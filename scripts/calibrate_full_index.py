import argparse
from dataclasses import asdict
import csv
import hashlib
from io import StringIO
import json
from pathlib import Path
import sys
import tarfile
import time
from urllib.request import urlopen

import faiss
import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ml_model'))
from landmark_ml import LandmarkPipeline
from landmark_ml.calibration import fit, index_signature, metrics, probability
from landmark_ml.full_archive import cache_archive
from landmark_ml.storage import require_space


def save(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    temporary.replace(path)


def status(root, phase, **values):
    payload = {'phase': phase, 'updated_unix': time.time(), **values}
    save(root / 'experiment-status.json', payload)
    print(json.dumps(payload), flush=True)


def collect(root, pipeline, per_split, exclude_manifests=()):
    manifest = root / 'manifest.json'
    if manifest.is_file():
        return json.loads(manifest.read_text(encoding='utf-8'))
    labels_path = root / 'recognition_solution_v2.1.csv'
    if not labels_path.exists():
        with urlopen('https://s3.amazonaws.com/google-landmark/ground_truth/recognition_solution_v2.1.csv', timeout=60) as response:
            labels_path.write_bytes(response.read(8 * 1024 * 1024))
    labels = {row['id']: row for row in csv.DictReader(StringIO(labels_path.read_text(encoding='utf-8')))}
    known = {str(r.landmark_id) for r in pipeline.index.references}
    photos = root / 'images'
    photos.mkdir(exist_ok=True)
    rows = []
    seen = []
    excluded = []
    excluded_ids = set()
    for previous in exclude_manifests:
        for row in json.loads(previous.read_text(encoding='utf-8')):
            if row.get('split') != 'test':
                continue
            excluded_ids.add(row['id'])
            path = previous.parent / row['image_path']
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with Image.open(path) as original:
                pixels = np.asarray(ImageOps.exif_transpose(original).convert('L').resize((9, 8)))
                visual = int.from_bytes(np.packbits((pixels[:, 1:] > pixels[:, :-1]).ravel()).tobytes(), 'big')
            seen.append((digest, visual))
    checkpoint = root / 'collection-state.json'
    next_archive = 0
    if checkpoint.is_file():
        state = json.loads(checkpoint.read_text(encoding='utf-8'))
        rows, seen, excluded, next_archive = state['rows'], state['seen'], state['excluded'], state['next_archive']
    for number in range(next_archive, 20):
        status(root, 'collecting_official_test_images', archive=number, collected=len(rows))
        archive_path = cache_archive(number, root, workers=4, split='test')
        with tarfile.open(archive_path, mode='r|', bufsize=1024 * 1024) as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith('.jpg'):
                    continue
                key = Path(member.name).stem
                label = labels.get(key)
                if label is None or key in excluded_ids or 'neon:' + key in pipeline.index._paths:
                    continue
                split = 'calibration' if label['Usage'] == 'Public' else 'test' if label['Usage'] == 'Private' else None
                correct_ids = [int(value) for value in label['landmarks'].split()]
                covered = any(str(i) in known for i in correct_ids)
                if split is None or sum(r['split'] == split and r['known_to_index'] == covered for r in rows) >= per_split // 2:
                    continue
                if member.size > 10 * 1024 * 1024:
                    excluded.append({'id': key, 'reason': 'size_limit'})
                    continue
                source = archive.extractfile(member)
                body = source.read()
                source.close()
                digest = hashlib.sha256(body).hexdigest()
                from io import BytesIO
                with Image.open(BytesIO(body)) as original:
                    image = ImageOps.exif_transpose(original).convert('L').resize((9, 8))
                    pixels = np.asarray(image)
                    visual = int.from_bytes(np.packbits((pixels[:, 1:] > pixels[:, :-1]).ravel()).tobytes(), 'big')
                if any(digest == other or (visual ^ previous).bit_count() <= 4 for other, previous in seen):
                    excluded.append({'id': key, 'reason': 'duplicate_or_query_near_duplicate'})
                    continue
                require_space(root, len(body))
                path = photos / (key + '.jpg')
                path.write_bytes(body)
                seen.append((digest, visual))
                rows.append({'id': key, 'image_path': 'images/' + path.name, 'split': split,
                             'landmark_ids': correct_ids, 'known_to_index': covered,
                             'sha256': digest, 'source_archive': number, 'source_usage': label['Usage']})
                if len(rows) % 100 == 0:
                    status(root, 'collecting_official_test_images', archive=number, collected=len(rows))
                if all(sum(r['split'] == split for r in rows) >= per_split for split in ['calibration', 'test']):
                    break
        save(checkpoint, {'rows': rows, 'seen': seen, 'excluded': excluded, 'next_archive': number + 1})
        archive_path.unlink()
        if len(rows) >= 2 * per_split:
            break
    if any(sum(r['split'] == split for r in rows) < per_split for split in ['calibration', 'test']):
        raise ValueError('Insufficient independent official test examples')
    save(manifest, rows)
    save(root / 'collection-exclusions.json', excluded)
    return rows


def evaluate(root, pipeline, rows):
    output = root / 'predictions.json'
    results = json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
    completed = {r['id'] for r in results}
    pending = [r for r in rows if r['id'] not in completed]
    for start in range(0, len(pending), 16):
        batch = pending[start:start + 16]
        vectors = pipeline.embedder.embed([root / r['image_path'] for r in batch])
        predictions = pipeline.index.predict_batch(vectors, top_k=5)
        for row, prediction in zip(batch, predictions):
            decision = pipeline.recognition_policy.evaluate(prediction)
            results.append({**row, 'candidate_landmark_id': prediction['landmark_id'],
                            'correct': prediction['landmark_id'] in row['landmark_ids'],
                            'match_score': prediction['match_score'], 'similarity': prediction['similarity'],
                            'agreement': prediction['agreement'], 'accepted': decision['accepted']})
        save(output, results)
        status(root, 'evaluating', evaluated=len(results), total=len(rows))
    return results


def summarize(rows, model):
    outcomes = [r['correct'] for r in rows]
    probabilities = [probability(model, r['match_score']) for r in rows]
    accepted = [r for r in rows if r['accepted']]
    displayed = [r for r in accepted if model['score_range'][0] <= r['match_score'] <= model['score_range'][1]]
    supported = [r for r in rows if r['known_to_index']]
    unknown = [r for r in rows if not r['known_to_index']]
    conditional = model.get('population') == 'accepted_predictions'
    return {'all_candidates': None if conditional else metrics(probabilities, outcomes),
            'raw_matching_score_as_probability': metrics([r['match_score'] for r in rows], outcomes),
            'constant_baseline': metrics([model['correct_count'] / model['sample_count']] * len(accepted), [r['correct'] for r in accepted]) if conditional and accepted else metrics([model['correct_count'] / model['sample_count']] * len(rows), outcomes),
            'acceptance_rate': len(accepted) / len(rows), 'accepted_count': len(accepted),
            'displayed_probability_count': len(displayed),
            'displayed_probability_metrics': metrics([probability(model, r['match_score']) for r in displayed], [r['correct'] for r in displayed]) if displayed else None,
            'accepted_candidates': metrics([probability(model, r['match_score']) for r in accepted], [r['correct'] for r in accepted]) if accepted else None,
            'supported_landmark_queries': len(supported), 'unsupported_queries': len(unknown),
            'supported_top_label_accuracy': float(np.mean([r['correct'] for r in supported])) if supported else None,
            'unsupported_false_acceptance_rate': float(np.mean([r['accepted'] for r in unknown])) if unknown else None,
            'probabilities_within_calibration_range': sum(model['score_range'][0] <= r['match_score'] <= model['score_range'][1] for r in rows)}


def main():
    import torch
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--model', default='dinov2-small')
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--per-split', type=int, default=400)
    parser.add_argument('--exclude-test-manifest', type=Path, nargs='*', default=[])
    parser.add_argument('--population', choices=['all_candidates', 'accepted_predictions'], default='accepted_predictions')
    args = parser.parse_args()
    if args.per_split < 100 or args.per_split % 2:
        parser.error('Use an even number of at least 100 examples per split')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    faiss.omp_set_num_threads(4)
    status(root, 'loading_full_index')
    pipeline = LandmarkPipeline.load(args.index, args.model, args.device)
    pipeline.calibrator = None
    pipeline.embedder.preprocess_workers = 4
    signature = index_signature(pipeline.index)
    configuration = {'index_signature': signature, 'recognition_policy': asdict(pipeline.recognition_policy),
                     'per_split': args.per_split, 'population': args.population, 'excluded_test_manifest_hashes': [hashlib.sha256(p.read_bytes()).hexdigest() for p in args.exclude_test_manifest], 'sampling': 'Half covered-landmark queries and half unsupported/non-landmark queries in each split', 'top_k': 5, 'dataset': 'GLDv2 recognition_solution_v2.1',
                     'split_rule': 'Public for calibration; Private for evaluation. Selection does not use model outcomes.'}
    config_path = root / 'configuration.json'
    if config_path.exists() and json.loads(config_path.read_text(encoding='utf-8')) != configuration:
        raise ValueError('Experiment configuration changed; use a fresh output directory')
    save(config_path, configuration)
    rows = collect(root, pipeline, args.per_split, args.exclude_test_manifest)
    results = evaluate(root, pipeline, rows)
    calibration = [r for r in results if r['split'] == 'calibration' and (args.population == 'all_candidates' or r['accepted'])]
    test = [r for r in results if r['split'] == 'test']
    try:
        model = fit([r['match_score'] for r in calibration], [r['correct'] for r in calibration])
    except ValueError as error:
        accepted = [r for r in test if r['accepted']]
        unsupported = [r for r in test if not r['known_to_index']]
        report = {**configuration, 'calibration_samples': len(calibration), 'test_samples': len(test),
                  'calibration_correct': sum(r['correct'] for r in calibration),
                  'calibration_incorrect': sum(not r['correct'] for r in calibration),
                  'calibration_fit_error': str(error), 'installed_in_runtime': False,
                  'test': {'accepted_count': len(accepted), 'acceptance_rate': len(accepted) / len(test),
                           'accepted_accuracy': sum(r['correct'] for r in accepted) / len(accepted) if accepted else None,
                           'unsupported_queries': len(unsupported),
                           'unsupported_false_acceptance_rate': sum(r['accepted'] for r in unsupported) / len(unsupported) if unsupported else None}}
        save(root / 'evaluation.json', report)
        status(root, 'evaluation_complete_insufficient_calibration', reason=str(error))
        return
    model.update(index_signature=signature, top_k=5, recognition_policy=asdict(pipeline.recognition_policy),
                 dataset=configuration['dataset'], population=args.population, deployment_status='not_approved', calibration_image_hashes=[r['sha256'] for r in calibration])
    save(root / 'calibration-candidate.json', model)
    report = {**configuration, 'calibration_samples': len(calibration), 'test_samples': len(test),
              'calibration_correct': sum(r['correct'] for r in calibration), 'calibration_incorrect': sum(not r['correct'] for r in calibration),
              'test': summarize(test, model), 'installed_in_runtime': False,
              'limitations': ['Balanced official benchmark subset: 50% covered-landmark and 50% unsupported/non-landmark queries. Not representative validation of frontend user uploads; probabilities depend on this mix.',
                              'Query IDs excluded from reference IDs; exact and near duplicates excluded within the query collection. Visual duplicates against all training photos were not exhaustively audited.',
                              'No thresholds or calibrator parameters tuned on the evaluation split.',
                              'Confidence is not automatically installed; review calibration, acceptance coverage, and uncertainty before deployment.']}
    save(root / 'evaluation.json', report)
    status(root, 'evaluation_complete_not_deployed', test=report['test'])


if __name__ == '__main__':
    main()
