import argparse
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
import os
import tarfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from .embeddings import DinoV2Embedder
from .full_index import commit_shard, finish, get_meta, open_ledger, put_meta, recover_shards, snapshot, status
from .retrieval import Reference, ReferenceIndex
from .storage import allocation_lock, require_space


def record_activity(directory, phase, **values):
    target = Path(directory) / 'activity.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps({'phase': phase, 'updated_unix': time.time(), **values}), encoding='utf-8')
    temporary.replace(target)


def stream_archive(number, offset, cache=None):
    if cache is not None:
        stream = Path(cache).open('rb')
        stream.seek(offset)
        return stream
    url = f'https://s3.amazonaws.com/google-landmark/train/images_{number:03d}.tar'
    request = Request(url, headers={'Range': f'bytes={offset}-', 'User-Agent': 'Trekmark-Capstone-Indexer/1.0'})
    response = urlopen(request, timeout=120)
    if offset and (response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')):
        response.close()
        raise RuntimeError('Archive source did not honor resume offset')
    return response


class ArchiveReader:
    def __init__(self, response):
        self.response = response
        headers = getattr(response, 'headers', {})
        self.expected = int(headers['Content-Length']) if headers.get('Content-Length') else None
        self.received = 0

    def read(self, amount):
        data = self.response.read(amount)
        self.received += len(data)
        return data

    def verify_complete(self):
        while self.read(1024 * 1024):
            pass
        if self.expected is not None and self.received != self.expected:
            raise EOFError('Archive connection ended before the expected byte count')


def process_archive(connection, directory, number, embedder, batch_size=16, shard_size=512, cache=None):
    row = connection.execute('SELECT offset,complete FROM archives WHERE number=?', (number,)).fetchone()
    if row and row['complete']:
        return
    offset = row['offset'] if row else 0
    current = ReferenceIndex(embedder.dimension, embedder.signature)
    records = []
    batch = []
    checkpoint_offset = offset

    def checkpoint(position):
        nonlocal current, records
        commit_shard(connection, directory, current, records)
        current = ReferenceIndex(embedder.dimension, embedder.signature)
        records = []
        connection.execute('INSERT OR REPLACE INTO archives VALUES (?,?,0)', (number, position))
        connection.commit()
        record_activity(directory, 'archive', archive=number, offset=position)

    def embed_batch():
        nonlocal batch
        if not batch:
            return
        try:
            vectors = embedder.embed([data for _, data in batch])
        except Exception:
            vectors = None
        for position, (image, data) in enumerate(batch):
            try:
                vector = vectors[position:position + 1] if vectors is not None else embedder.embed([data])
                current.add(vector, [Reference(int(image['landmark_id']), 'neon:' + image['id'])])
                records.append({'id': image['id'], 'landmark_id': image['landmark_id'], 'url': image['url'], 'archive': number})
                connection.execute("UPDATE images SET state='buffered',error=NULL WHERE id=?", (image['id'],))
            except Exception as error:
                connection.execute("UPDATE images SET state='unavailable',error=? WHERE id=?", (json.dumps({'type': type(error).__name__, 'reason': str(error)[:500], 'source': 'official_archive'}), image['id']))
        connection.commit()
        batch = []

    with (stream_archive(number, offset, cache) if cache is not None else stream_archive(number, offset)) as response:
        reader = ArchiveReader(response)
        with tarfile.open(fileobj=reader, mode='r|', bufsize=1024 * 1024) as archive:
            for member in archive:
                checkpoint_offset = offset + member.offset_data + ((member.size + 511) // 512) * 512
                if not member.isfile() or not member.name.lower().endswith('.jpg'):
                    continue
                image_id = Path(member.name).stem
                image = connection.execute("SELECT id,url,landmark_id FROM images WHERE id=? AND state NOT IN ('indexed','buffered')", (image_id,)).fetchone()
                if image is None:
                    continue
                if member.size > 10 * 1024 * 1024:
                    connection.execute("UPDATE images SET state='unavailable',error=? WHERE id=?", ('Image exceeds 10 MB', image_id))
                    connection.commit()
                    continue
                extracted = archive.extractfile(member)
                data = extracted.read() if extracted else b''
                if extracted:
                    extracted.close()
                batch.append((image, data))
                if len(batch) >= batch_size:
                    embed_batch()
                if len(records) >= shard_size:
                    checkpoint(checkpoint_offset)
            embed_batch()
            checkpoint(checkpoint_offset)
        reader.verify_complete()
    connection.execute('INSERT OR REPLACE INTO archives VALUES (?,?,1)', (number, checkpoint_offset))
    connection.commit()


def cache_archive(number, directory, workers=4, split='train'):
    if split not in ('train', 'test'):
        raise ValueError('Unsupported archive split')
    root = Path(directory).resolve() / 'archive-cache'
    root.mkdir(exist_ok=True)
    destination = root / f'images_{number:03d}.tar'
    if destination.is_file():
        return destination
    partial = destination.with_suffix('.part')
    progress = destination.with_suffix('.chunks.json')
    url = f'https://s3.amazonaws.com/google-landmark/{split}/images_{number:03d}.tar'
    request = Request(url, headers={'Range': 'bytes=0-0'})
    with urlopen(request, timeout=30) as response:
        content_range = response.headers.get('Content-Range', '')
        if response.status != 206 or '/' not in content_range:
            raise ValueError('Archive endpoint must support byte ranges')
        size = int(content_range.rsplit('/', 1)[1])
        response.read(1)
    chunk_size = 8 * 1024 * 1024
    state = json.loads(progress.read_text()) if progress.exists() else {'size': size, 'chunk_size': chunk_size, 'complete': []}
    if state['size'] != size or state['chunk_size'] != chunk_size:
        raise ValueError('Archive size differs from the saved download')
    with allocation_lock:
        require_space(root, max(0, size - (partial.stat().st_size if partial.exists() else 0)))
        with partial.open('r+b' if partial.exists() else 'wb') as stream:
            stream.truncate(size)
    complete = set(state['complete'])
    mutex = threading.Lock()

    def fetch_chunk(number_chunk):
        start = number_chunk * chunk_size
        end = min(size, start + chunk_size) - 1
        for attempt in range(4):
            try:
                request = Request(url, headers={'Range': f'bytes={start}-{end}'})
                with urlopen(request, timeout=60) as response:
                    expected = f'bytes {start}-{end}/{size}'
                    if response.status != 206 or response.headers.get('Content-Range') != expected:
                        raise ValueError('Archive range response does not match the requested bytes')
                    data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise EOFError('Truncated archive chunk')
                with partial.open('r+b') as stream:
                    stream.seek(start)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                with mutex:
                    complete.add(number_chunk)
                    state['complete'] = sorted(complete)
                    temporary = progress.with_suffix('.tmp')
                    temporary.write_text(json.dumps(state), encoding='utf-8')
                    temporary.replace(progress)
                return
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
    chunks = (size + chunk_size - 1) // chunk_size
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fetch_chunk, [i for i in range(chunks) if i not in complete]))
    checksum_url = f'https://s3.amazonaws.com/google-landmark/md5sum/{split}/md5.images_{number:03d}.txt'
    with urlopen(checksum_url, timeout=30) as response:
        expected = response.read(4096).decode().split()[0]
    actual = hashlib.md5()
    with partial.open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            actual.update(block)
    if actual.hexdigest() != expected:
        (root / f'images_{number:03d}.checksum-error.json').write_text(json.dumps({'expected': expected, 'actual': actual.hexdigest()}))
        progress.unlink(missing_ok=True)
        partial.unlink()
        raise ValueError('Official archive checksum mismatch')
    partial.rename(destination)
    progress.unlink(missing_ok=True)
    print(json.dumps({'archive': number, 'phase': 'download_verified', 'bytes': destination.stat().st_size}), flush=True)
    return destination


def main():
    from dotenv import load_dotenv
    import torch
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--model', default='dinov2-small')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--prefetch', type=int, default=2)
    parser.add_argument('--download-workers', type=int, default=4)
    parser.add_argument('--float32', action='store_true')
    parser.add_argument('--preprocess-workers', type=int, default=4)
    args = parser.parse_args()
    if min(args.batch_size, args.threads, args.prefetch, args.download_workers) < 1:
        parser.error('Batch size, threads and prefetch must be positive')
    torch.set_num_threads(args.threads)
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'shards').mkdir(exist_ok=True)
    lock = (directory / 'run.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        connection = open_ledger(directory)
        snapshot(connection, os.environ['DATABASE_URL'])
        connection.execute('CREATE TABLE IF NOT EXISTS archives (number INTEGER PRIMARY KEY, offset INTEGER NOT NULL, complete INTEGER NOT NULL)')
        connection.commit()
        embedder = DinoV2Embedder(args.model, args.device, mixed_precision=not args.float32, preprocess_workers=args.preprocess_workers)
        put_meta(connection, 'inference_precision', 'cuda_autocast_fp16' if embedder.mixed_precision else 'float32')
        if get_meta(connection, 'signature') not in (None, embedder.signature):
            raise ValueError('Model differs from existing checkpoints')
        put_meta(connection, 'signature', embedder.signature)
        recover_shards(connection, directory)
        connection.execute("UPDATE images SET state='pending' WHERE state='buffered'")
        connection.commit()
        put_meta(connection, 'run_start_embedded', connection.execute("SELECT count(*) FROM images WHERE state='indexed'").fetchone()[0])
        started = time.monotonic()
        stop = threading.Event()

        def heartbeat():
            while not stop.wait(30):
                reader = open_ledger(directory)
                try:
                    status(reader, directory, started, 'streaming_official_archives')
                finally:
                    reader.close()

        heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        heartbeat_thread.start()
        downloads = ThreadPoolExecutor(max_workers=args.prefetch)
        futures = {}
        completed = {row[0] for row in connection.execute('SELECT number FROM archives WHERE complete=1')}
        for number in completed:
            cached = directory / 'archive-cache' / f'images_{number:03d}.tar'
            if cached.is_file() and cached.resolve().is_relative_to(directory):
                cached.unlink()
        todo = [number for number in range(500) if number not in completed]
        try:
            for position, number in enumerate(todo):
                for upcoming in todo[position:position + args.prefetch]:
                    if upcoming not in futures:
                        futures[upcoming] = downloads.submit(cache_archive, upcoming, directory, args.download_workers)
                attempt = 0
                while True:
                    try:
                        print(json.dumps({'archive': number, 'phase': 'reading_archive'}), flush=True)
                        record_activity(directory, 'archive', archive=number)
                        cache = futures[number].result()
                        process_archive(connection, directory, number, embedder, args.batch_size, cache=cache)
                        cache.unlink()
                        del futures[number]
                        break
                    except Exception as error:
                        recover_shards(connection, directory)
                        connection.execute("UPDATE images SET state='pending' WHERE state='buffered'")
                        connection.commit()
                        attempt += 1
                        print(json.dumps({'archive': number, 'error': type(error).__name__, 'reason': str(error)[:500], 'retry': attempt}), flush=True)
                        futures[number] = downloads.submit(cache_archive, number, directory, args.download_workers)
                        time.sleep(min(3600, 30 * 2 ** min(attempt, 7)))
            connection.execute("UPDATE images SET state='pending',next_attempt=0 WHERE state IN ('pending','retry')")
            connection.commit()
            remaining = connection.execute("SELECT count(*) FROM images WHERE state='pending'").fetchone()[0]
            if remaining:
                status(connection, directory, started, 'archive_pass_done_source_fallback_needed')
                put_meta(connection, 'archive_pass_complete', True)
            else:
                stop.set()
                heartbeat_thread.join()
                record_activity(directory, 'exporting')
                finish(connection, directory, embedder, started)
        finally:
            downloads.shutdown(wait=True)
            stop.set()
            heartbeat_thread.join()
            connection.close()
    finally:
        lock.close()
    if remaining:
        record_activity(directory, 'source_fallback')
        from .full_index import run
        run(directory, os.environ['DATABASE_URL'], args.model, batch_size=args.batch_size, threads=args.threads, interval=1)
    record_activity(directory, 'validating_and_packaging')
    from .compact import prepare_handoff
    prepare_handoff(directory)


if __name__ == '__main__':
    main()
