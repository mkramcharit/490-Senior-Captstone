import hashlib
import json
import sqlite3
import zipfile
from uuid import uuid4
from pathlib import Path

import faiss
import numpy as np

from .indexing import export_index
from .retrieval import ReferenceIndex
from .storage import require_space


def validate_master(index, directory):
    connection = sqlite3.connect(Path(directory) / 'ledger.sqlite')
    connection.row_factory = sqlite3.Row
    counts = dict(connection.execute('SELECT state,count(*) FROM images GROUP BY state'))
    if counts.get('pending', 0) or counts.get('retry', 0) or counts.get('buffered', 0):
        raise ValueError('Full source pass is not finished')
    if counts.get('indexed', 0) != index.index.ntotal:
        raise ValueError('Index count differs from ledger')
    expected = {row['id']: row['landmark_id'] for row in connection.execute("SELECT id,landmark_id FROM images WHERE state='indexed'")}
    for ref in index.references:
        key = ref.image_path.removeprefix('neon:')
        if expected.pop(key, None) != ref.landmark_id:
            raise ValueError('Reference does not match the original Neon label')
    if expected:
        raise ValueError('Some indexed rows are absent from the mapping')
    for start in range(0, index.index.ntotal, 8192):
        vectors = index.index.reconstruct_n(start, min(8192, index.index.ntotal - start))
        if not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4):
            raise ValueError('Embeddings are not finite unit vectors')
    source = json.loads(connection.execute("SELECT value FROM metadata WHERE key='source_counts'").fetchone()[0])
    if sum(counts.values()) != source['rows']:
        raise ValueError('Source accounting is incomplete')
    coverage = {'source': source, 'counts': counts, 'indexed_landmarks': len({r.landmark_id for r in index.references}),
                'all_source_rows_accounted_for': True, 'dimension': index.index.d}
    connection.close()
    return coverage


def labels_for_scores(scores, positions, references, exclude=None):
    groups = {}
    for score, position in zip(scores, positions):
        if position < 0 or position == exclude:
            continue
        key = references[int(position)].landmark_id
        groups.setdefault(key, []).append(float(score))
        if sum(len(v) for v in groups.values()) == 5:
            break
    return max(groups, key=lambda key: (sum(max(0, s) for s in groups[key]), max(groups[key]))) if groups else None


def approximation_report(master, compact, queries, query_ids, exact_scores, exact_positions):
    scores, positions = compact.search(queries, 12)
    recall = []
    agreement = []
    for i, query_id in enumerate(query_ids):
        expected = [int(p) for p in exact_positions[i] if p != query_id and p >= 0][:10]
        actual = [int(p) for p in positions[i] if p != query_id and p >= 0][:10]
        recall.append(len(set(expected).intersection(actual)) / max(1, len(expected)))
        agreement.append(labels_for_scores(scores[i], positions[i], master.references, query_id) == labels_for_scores(exact_scores[i], exact_positions[i], master.references, query_id))
    return {'neighbor_recall_at_10': float(np.mean(recall)), 'landmark_decision_agreement': float(np.mean(agreement)),
            'query_count': len(queries), 'scope': 'Approximation compared with the full-precision index, excluding each query reference itself; not independent recognition accuracy.'}


def compact_index(master, target, sample_count=65536, query_count=256):
    count = master.index.ntotal
    train_ids = np.linspace(0, count - 1, min(count, sample_count), dtype=np.int64)
    training = master.index.reconstruct_batch(train_ids)
    query_ids = np.linspace(0, count - 1, min(count, query_count), dtype=np.int64)
    queries = master.index.reconstruct_batch(query_ids)
    exact_scores, exact_positions = master.index.search(queries, min(12, count))
    chosen = None
    report = None
    for parts in (64, 96, 128):
        if master.index.d % parts or count < 10000:
            continue
        candidate = faiss.IndexPQ(master.index.d, parts, 8, faiss.METRIC_INNER_PRODUCT)
        candidate.pq.cp.niter = 15
        candidate.train(training)
        for start in range(0, count, 8192):
            candidate.add(master.index.reconstruct_n(start, min(8192, count - start)))
        metrics = approximation_report(master, candidate, queries, query_ids, exact_scores, exact_positions)
        print(json.dumps({'phase': 'compact_validation', 'product_quantizer_bytes': parts, **metrics}), flush=True)
        if metrics['neighbor_recall_at_10'] >= .9 and metrics['landmark_decision_agreement'] >= .98:
            chosen = candidate
            report = {'format': 'product_quantization', 'bytes_per_vector': parts, **metrics}
            break
    if chosen is None:
        chosen = faiss.IndexScalarQuantizer(master.index.d, faiss.ScalarQuantizer.QT_8bit, faiss.METRIC_INNER_PRODUCT)
        chosen.train(training)
        for start in range(0, count, 8192):
            chosen.add(master.index.reconstruct_n(start, min(8192, count - start)))
        metrics = approximation_report(master, chosen, queries, query_ids, exact_scores, exact_positions)
        if metrics['neighbor_recall_at_10'] < .95 or metrics['landmark_decision_agreement'] < .98:
            raise ValueError('Compact index did not meet approximation checks; full-precision master is preserved')
        report = {'format': 'scalar_quantization_8bit', 'bytes_per_vector': master.index.d, **metrics}
    result = ReferenceIndex(master.index.d, master.signature)
    result.index = chosen
    result.references = master.references
    result._paths = master._paths
    require_space(Path(target).parent, count * (master.index.d + 2048))
    export_index(result, target)
    report.update(vector_count=count, dimension=master.index.d, confidence_calibrated=False)
    (Path(target) / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def prepare_handoff(directory):
    directory = Path(directory).resolve()
    faiss.omp_set_num_threads(4)
    payload = json.loads((directory / 'bundle/references.json').read_text(encoding='utf-8'))
    master = ReferenceIndex.load(directory / 'bundle', payload['signature'])
    coverage = validate_master(master, directory)
    target = directory / 'handoff'
    published = target
    if not (published / 'build.json').is_file():
        target = directory / ('handoff-staging-' + uuid4().hex)
        report = compact_index(master, target)
        report.update(coverage=coverage)
        (target / 'build.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        with (target / 'HANDOFF.txt').open('w', encoding='utf-8') as stream:
            stream.write('Use the latest landmark_ml package from this branch. Point LANDMARK_INDEX_PATH to this extracted folder. Use the same dinov2-small weights already supplied with the project. images.faiss is the canonical FAISS index. Its identical alternate filename landmarks.index is omitted from the ZIP to avoid doubling the transfer size; no alias is needed by LandmarkPipeline. The mapping preserves Neon landmark IDs. No Python environment, image archive, or checkpoint is needed on the receiving computer. This expanded index is not probability-calibrated; confidence is null. match_score is a raw matching score, not a correctness probability. Unreliable matches return an unknown result. validation.json compares compact retrieval against the full-precision master, not ground-truth recognition accuracy. build.json contains actual coverage and unavailable-source counts.\n')
        if published.exists():
            published.rename(directory / ('handoff-incomplete-' + uuid4().hex))
        target.rename(published)
    target = published
    compact = ReferenceIndex.load(target, master.signature)
    if compact.references != master.references:
        raise ValueError('Existing handoff mapping differs from the completed master; export to a fresh directory')
    del compact
    archive = directory / 'teammate-index.zip'
    if not archive.exists():
        require_space(directory, sum(p.stat().st_size for p in target.iterdir() if p.is_file() and p.name != 'landmarks.index'))
        staging = directory / 'teammate-index.partial.zip'
        with zipfile.ZipFile(staging, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as zipped:
            for path in sorted(target.iterdir()):
                if path.is_file():
                    if path.name != 'landmarks.index':
                        zipped.write(path, arcname=path.name)
        with zipfile.ZipFile(staging) as zipped:
            if zipped.testzip() is not None:
                raise ValueError('Final ZIP failed integrity validation')
        staging.rename(archive)
    from .artifacts import sha256_file, sha256_stream
    with zipfile.ZipFile(archive) as zipped:
        for path in target.iterdir():
            if path.is_file() and path.name != 'landmarks.index':
                try:
                    with zipped.open(path.name) as stream:
                        if sha256_stream(stream) != sha256_file(path):
                            raise ValueError('Existing handoff ZIP differs from the runtime index; create a fresh package')
                except KeyError as error:
                    raise ValueError('Existing handoff ZIP is incomplete; create a fresh package') from error
    digest = hashlib.sha256()
    with archive.open('rb') as stream:
        while data := stream.read(4 * 1024 * 1024):
            digest.update(data)
    summary = {'phase': 'handoff_ready', 'archive': str(archive), 'bytes': archive.stat().st_size,
               'sha256': digest.hexdigest(), 'coverage': coverage}
    (directory / 'handoff-ready.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)
    return summary
