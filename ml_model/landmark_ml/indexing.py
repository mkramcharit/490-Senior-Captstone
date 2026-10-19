import json
import os
import pickle
import shutil
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from time import sleep

from PIL import Image

from .embeddings import DinoV2Embedder
from .retrieval import Reference, ReferenceIndex


def export_index(index, output):
    output = Path(output)
    if not all(type(ref.landmark_id) is int for ref in index.references):
        raise ValueError('Neon landmark IDs must be integers')
    index.save(output)
    shutil.copyfile(output / 'images.faiss', output / 'landmarks.index')
    with (output / 'landmark_ids.pkl').open('wb') as stream:
        pickle.dump([ref.landmark_id for ref in index.references], stream, protocol=4)


def download_image(url, timeout=20):
    if url.startswith('http://'):
        url = 'https://' + url[7:]
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Expected an HTTPS image URL without credentials')
    request = Request(url, headers={'User-Agent': 'Trekmark-Indexer/1.0'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                data = response.read(10 * 1024 * 1024 + 1)
            break
        except HTTPError as error:
            if attempt == 2 or error.code not in (429, 500, 502, 503, 504):
                raise
            sleep(2 ** attempt)
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            sleep(2 ** attempt)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('Image exceeds 10 MB')
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > 25_000_000:
            raise ValueError('Image exceeds 25 million pixels')
        image.verify()
    return data


def fetch_rows(connection, after, batch_size, landmark_ids=None):
    conditions = ['url IS NOT NULL', 'landmark_id IS NOT NULL']
    parameters = []
    if after is not None:
        conditions.append('id > %s')
        parameters.append(after)
    if landmark_ids:
        conditions.append('landmark_id = ANY(%s)')
        parameters.append(landmark_ids)
    parameters.append(batch_size)
    query = 'SELECT id, url, landmark_id FROM public.training_data WHERE '
    query += ' AND '.join(conditions) + ' ORDER BY id LIMIT %s'
    return connection.execute(query, parameters).fetchall()


def process_rows(rows, embedder, batch_size, workers, downloader=download_image):
    index = ReferenceIndex(embedder.dimension, embedder.signature)
    failures = []

    def fetch(row):
        try:
            return row, downloader(row['url']), None
        except Exception as error:
            return row, None, {'type': type(error).__name__, 'status': getattr(error, 'code', None)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(rows), batch_size):
            downloaded = list(pool.map(fetch, rows[start:start + batch_size]))
            valid = []
            for row, data, error in downloaded:
                if error:
                    failures.append({'id': row['id'], 'stage': 'download', 'error': error})
                else:
                    valid.append((row, data))
            if not valid:
                continue
            references = [Reference(int(row['landmark_id']), 'neon:' + str(row['id'])) for row, _ in valid]
            try:
                vectors = embedder.embed([data for _, data in valid])
            except Exception:
                for (row, data), reference in zip(valid, references):
                    try:
                        index.add(embedder.embed([data]), [reference])
                    except Exception as error:
                        failures.append({'id': row['id'], 'stage': 'embedding', 'error': type(error).__name__})
            else:
                index.add(vectors, references)
    return index, failures


def merge_shards(work, embedder, output):
    result = ReferenceIndex(embedder.dimension, embedder.signature)
    for checkpoint in sorted(Path(work).glob('batch-*')):
        if not (checkpoint / 'images.faiss').is_file():
            continue
        shard = ReferenceIndex.load(checkpoint, embedder.signature)
        result.add(shard.index.reconstruct_n(0, shard.index.ntotal), shard.references)
    export_index(result, output)
    return result


def build_from_neon(output, model_path='dinov2-small', device='cpu', fetch_size=256,
                    batch_size=16, workers=4, limit=None, landmark_ids=None, resume=False,
                    database_url=None):
    import psycopg
    from psycopg.rows import dict_row

    if min(fetch_size, batch_size, workers) < 1 or (limit is not None and limit < 1):
        raise ValueError('Batch sizes, workers, and limit must be positive')
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Choose a new output directory')
    work = output.with_name(output.name + '.work')
    if work.exists() and not resume:
        raise FileExistsError('Checkpoint directory exists; use --resume')
    if resume and not work.is_dir():
        raise FileNotFoundError('No checkpoint directory to resume')
    database_url = database_url or os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError('Set DATABASE_URL before indexing')
    embedder = DinoV2Embedder(model_path, device)
    from hashlib import sha256
    database_identity = urlparse(database_url)
    configuration = {'signature': embedder.signature, 'landmark_ids': landmark_ids or [],
                     'database': sha256((str(database_identity.hostname) + database_identity.path).encode()).hexdigest()}
    work.mkdir(parents=True, exist_ok=True)
    config_path = work / 'configuration.json'
    if config_path.exists():
        if json.loads(config_path.read_text()) != configuration:
            raise ValueError('Resume requires the same model and landmark selection')
    else:
        config_path.write_text(json.dumps(configuration), encoding='utf-8')
    after = None
    processed = 0
    checkpoints = sorted(work.glob('batch-*'))
    for checkpoint in checkpoints:
        progress = json.loads((checkpoint / 'progress.json').read_text())
        after = progress['last_id']
        processed += progress['row_count']
    sequence = len(checkpoints)
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row, connect_timeout=15) as connection:
        connection.execute('SET default_transaction_read_only = on')
        connection.execute('SET statement_timeout = 60000')
        while limit is None or processed < limit:
            size = fetch_size if limit is None else min(fetch_size, limit - processed)
            rows = fetch_rows(connection, after, size, landmark_ids)
            if not rows:
                break
            shard, failures = process_rows(rows, embedder, batch_size, workers)
            staging = work / ('pending-' + uuid4().hex)
            if shard.references:
                shard.save(staging)
            else:
                staging.mkdir()
            (staging / 'failures.json').write_text(json.dumps(failures, indent=2), encoding='utf-8')
            provenance = [{'id': row['id'], 'url': row['url'], 'landmark_id': row['landmark_id']} for row in rows]
            (staging / 'sources.json').write_text(json.dumps(provenance), encoding='utf-8')
            progress = {'last_id': rows[-1]['id'], 'row_count': len(rows), 'indexed_count': len(shard.references)}
            (staging / 'progress.json').write_text(json.dumps(progress), encoding='utf-8')
            staging.rename(work / f'batch-{sequence:09d}')
            sequence += 1
            after = rows[-1]['id']
            processed += len(rows)
            print(json.dumps({'rows_processed': processed, 'indexed_in_batch': len(shard.references), 'failed_in_batch': len(failures)}), flush=True)
    destination = work / ('assembled-' + uuid4().hex)
    result = merge_shards(work, embedder, destination)
    report = {'processed_rows': processed, 'indexed_images': len(result.references),
              'dimension': embedder.dimension, 'model_signature': embedder.signature,
              'confidence_calibrated': False, 'checkpoint_directory': str(work)}
    (destination / 'build.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    destination.rename(output)
    return report
