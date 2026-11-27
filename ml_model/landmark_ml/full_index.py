import argparse
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from .embeddings import DinoV2Embedder
from .indexing import export_index
from .retrieval import Reference, ReferenceIndex
from .storage import allocation_lock, require_space


class DownloadGate:
    def __init__(self, interval=.25):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_request = 0
        self.blocked_until = 0

    def wait(self):
        while True:
            with self.lock:
                now = time.monotonic()
                delay = max(self.next_request, self.blocked_until) - now
                if delay <= 0:
                    self.next_request = now + self.interval
                    return
            time.sleep(min(delay, 10))

    def block(self, seconds):
        with self.lock:
            self.blocked_until = max(self.blocked_until, time.monotonic() + seconds)


def image_url(source):
    source = source.replace('http://', 'https://', 1)
    parsed = urlparse(source)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid HTTPS image URL')
    if parsed.hostname == 'upload.wikimedia.org' and '/commons/' in parsed.path:
        tail = parsed.path.split('/commons/', 1)[1]
        if tail.startswith('thumb/'):
            tail = tail[6:].rsplit('/', 1)[0]
        filename = tail.rsplit('/', 1)[-1]
        suffix = '.png' if filename.lower().endswith('.svg') else '.jpg' if filename.lower().endswith(('.tif', '.tiff')) else ''
        return 'https://upload.wikimedia.org/wikipedia/commons/thumb/' + tail + '/500px-' + filename + suffix
    return source


def download(source, gate):
    gate.wait()
    request = Request(image_url(source), headers={'User-Agent': 'Trekmark-Capstone-Indexer/1.0 (academic landmark recognition)'})
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read(10 * 1024 * 1024 + 1)
    except HTTPError as error:
        if error.code == 429:
            try:
                delay = max(60, float(error.headers.get('Retry-After', '60')))
            except ValueError:
                delay = 60
            gate.block(delay)
        raise
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('Image exceeds 10 MB')
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > 25_000_000:
            raise ValueError('Image exceeds 25 million pixels')
        image.verify()
    return data


def open_ledger(directory):
    connection = sqlite3.connect(Path(directory) / 'ledger.sqlite')
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('PRAGMA cache_size=-131072')
    connection.execute('PRAGMA mmap_size=1073741824')
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS images (
            id TEXT PRIMARY KEY, url TEXT NOT NULL, landmark_id INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt REAL NOT NULL DEFAULT 0, error TEXT, shard TEXT
        );
        CREATE INDEX IF NOT EXISTS pending_images ON images(state, next_attempt, id);
        CREATE INDEX IF NOT EXISTS landmark_images ON images(landmark_id, state);
    ''')
    return connection


def put_meta(connection, key, value):
    connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, json.dumps(value)))
    connection.commit()


def get_meta(connection, key):
    row = connection.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def snapshot(connection, database_url):
    import psycopg
    if get_meta(connection, 'snapshot_complete'):
        return
    with psycopg.connect(database_url, connect_timeout=15) as source:
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        source.execute('SET statement_timeout=120000')
        counts = source.execute('SELECT count(*), count(DISTINCT landmark_id) FROM public.training_data WHERE url IS NOT NULL AND landmark_id IS NOT NULL').fetchone()
        put_meta(connection, 'source_counts', {'rows': counts[0], 'landmarks': counts[1]})
        with source.cursor(name='trekmark_full_index') as cursor:
            cursor.execute('SELECT id,url,landmark_id FROM public.training_data WHERE url IS NOT NULL AND landmark_id IS NOT NULL ORDER BY id')
            while True:
                rows = cursor.fetchmany(5000)
                if not rows:
                    break
                connection.executemany('INSERT OR IGNORE INTO images(id,url,landmark_id) VALUES (?,?,?)', [(str(r[0]), r[1], int(r[2])) for r in rows])
                connection.commit()
                count = connection.execute('SELECT count(*) FROM images').fetchone()[0]
                print(json.dumps({'phase': 'snapshot', 'rows': count, 'expected': counts[0]}), flush=True)
    actual = connection.execute('SELECT count(*) FROM images').fetchone()[0]
    if actual != counts[0]:
        raise RuntimeError('Source changed during snapshot recovery; inspect the ledger before continuing')
    put_meta(connection, 'snapshot_complete', True)


def commit_shard(connection, directory, index, records):
    if not records:
        return
    name = 'shard-' + uuid4().hex
    target = Path(directory) / 'shards' / name
    with allocation_lock:
        require_space(directory, index.index.ntotal * (index.index.d * 4 + 2048))
        index.save(target)
    (target / 'records.json').write_text(json.dumps(records), encoding='utf-8')
    (target / 'ready').write_text('ready', encoding='utf-8')
    with connection:
        connection.executemany("UPDATE images SET state='indexed',shard=?,error=NULL WHERE id=? AND state!='indexed'", [(name, row['id']) for row in records])
    (target / 'committed').write_text('committed', encoding='utf-8')


def recover_shards(connection, directory):
    for path in sorted((Path(directory) / 'shards').glob('shard-*')):
        if not (path / 'ready').is_file() or (path / 'committed').is_file():
            continue
        records = json.loads((path / 'records.json').read_text(encoding='utf-8'))
        with connection:
            connection.executemany("UPDATE images SET state='indexed',shard=?,error=NULL WHERE id=?", [(path.name, row['id']) for row in records])
        (path / 'committed').write_text('committed', encoding='utf-8')


def status(connection, directory, started, phase='indexing'):
    counts = dict(connection.execute('SELECT state,count(*) FROM images GROUP BY state').fetchall())
    indexed_landmarks = connection.execute("SELECT count(DISTINCT landmark_id) FROM images WHERE state='indexed'").fetchone()[0]
    result = {'phase': phase, 'updated_utc': datetime.now(timezone.utc).isoformat(),
              'source': get_meta(connection, 'source_counts'), 'counts': counts,
              'indexed_landmarks': indexed_landmarks, 'elapsed_seconds_this_run': round(time.monotonic() - started, 1),
              'confidence_calibrated': False}
    baseline = get_meta(connection, 'run_start_embedded') or 0
    elapsed = max(1, time.monotonic() - started)
    newly_embedded = max(0, counts.get('indexed', 0) + counts.get('buffered', 0) - baseline)
    result['images_per_second_this_run'] = round(newly_embedded / elapsed, 2)
    remaining = counts.get('pending', 0) + counts.get('retry', 0)
    result['estimated_remaining_hours_at_this_rate'] = round(remaining / (newly_embedded / elapsed) / 3600, 2) if newly_embedded > 1000 else None
    target = Path(directory) / 'status.json'
    temporary = target.with_name('status-' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
    temporary.replace(target)
    print(json.dumps(result), flush=True)
    return result


def finish(connection, directory, embedder, started):
    output = Path(directory) / 'bundle'
    if output.exists():
        return status(connection, directory, started, 'finished_with_coverage_report')
    result = ReferenceIndex(embedder.dimension, embedder.signature)
    names = connection.execute("SELECT DISTINCT shard FROM images WHERE state='indexed' ORDER BY shard").fetchall()
    for (name,) in names:
        shard = ReferenceIndex.load(Path(directory) / 'shards' / name, embedder.signature)
        result.add(shard.index.reconstruct_n(0, shard.index.ntotal), shard.references)
    expected = connection.execute("SELECT count(*) FROM images WHERE state='indexed'").fetchone()[0]
    if result.index.ntotal != expected:
        raise RuntimeError('Vector and ledger counts disagree')
    staging = Path(directory) / ('export-' + uuid4().hex)
    with allocation_lock:
        require_space(directory, expected * (embedder.dimension * 4 + 2048))
        export_index(result, staging)
    report = status(connection, directory, started, 'exporting')
    report['phase'] = 'finished_with_coverage_report'
    (staging / 'build.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with (staging / 'unavailable.jsonl').open('w', encoding='utf-8') as stream:
        for row in connection.execute("SELECT id,url,landmark_id,state,error FROM images WHERE state!='indexed'"):
            stream.write(json.dumps(dict(row)) + '\n')
    missing = connection.execute("SELECT DISTINCT landmark_id FROM images EXCEPT SELECT DISTINCT landmark_id FROM images WHERE state='indexed'").fetchall()
    (staging / 'missing_landmark_ids.json').write_text(json.dumps([r[0] for r in missing]), encoding='utf-8')
    for attempt in range(8):
        try:
            staging.rename(output)
            break
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(.2 * 2 ** attempt)
    return status(connection, directory, started, 'finished_with_coverage_report')


def run(directory, database_url, model='dinov2-small', batch_size=16, shard_size=1024, workers=4, interval=.25, threads=4, max_rows=None, embedder=None, downloader=None):
    import torch
    torch.set_num_threads(threads)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'shards').mkdir(exist_ok=True)
    lock = (directory / 'run.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            if lock.tell() == 0:
                lock.write(b'0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        connection = open_ledger(directory)
        identity = sha256((str(urlparse(database_url).hostname) + urlparse(database_url).path).encode()).hexdigest()
        if get_meta(connection, 'database') not in (None, identity):
            raise ValueError('Ledger belongs to a different database')
        put_meta(connection, 'database', identity)
        snapshot(connection, database_url)
        embedder = embedder or DinoV2Embedder(model)
        if get_meta(connection, 'signature') not in (None, embedder.signature):
            raise ValueError('Resume requires identical model weights and preprocessing')
        put_meta(connection, 'signature', embedder.signature)
        recover_shards(connection, directory)
        connection.execute("UPDATE images SET state='pending' WHERE state='buffered'")
        connection.commit()
        gate = DownloadGate(interval)
        downloader = downloader or (lambda url: download(url, gate))
        current = ReferenceIndex(embedder.dimension, embedder.signature)
        records = []
        attempted = 0
        last_status = 0

        def fetch(row):
            try:
                return row, downloader(row['url']), None
            except Exception as error:
                code = getattr(error, 'code', None)
                permanent = code in (404, 410) or isinstance(error, (ValueError, UnidentifiedImageError))
                return row, None, {'type': type(error).__name__, 'status': code,
                                  'reason': str(getattr(error, 'reason', error))[:500], 'permanent': permanent}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            while True:
                rows = connection.execute("SELECT id,url,landmark_id,attempts FROM images WHERE state IN ('pending','retry') AND next_attempt<=? ORDER BY next_attempt,id LIMIT ?", (time.time(), batch_size)).fetchall()
                if not rows:
                    commit_shard(connection, directory, current, records)
                    current = ReferenceIndex(embedder.dimension, embedder.signature)
                    records = []
                    remaining = connection.execute("SELECT count(*) FROM images WHERE state IN ('pending','retry')").fetchone()[0]
                    if not remaining:
                        return finish(connection, directory, embedder, started)
                    status(connection, directory, started, 'waiting_for_retry')
                    if max_rows is not None and attempted >= max_rows:
                        return
                    time.sleep(30)
                    continue
                downloaded = list(pool.map(fetch, rows))
                valid = []
                for row, data, error in downloaded:
                    attempted += 1
                    if error:
                        attempts = row['attempts'] + 1
                        delay = min(3600, 60 * 2 ** min(attempts - 1, 6))
                        connection.execute('UPDATE images SET state=?,attempts=?,next_attempt=?,error=? WHERE id=?', ('unavailable' if error['permanent'] else 'retry', attempts, time.time() + delay, json.dumps(error), row['id']))
                    else:
                        valid.append((row, data))
                if valid:
                    try:
                        vectors = embedder.embed([data for _, data in valid])
                    except Exception:
                        vectors = None
                    for offset, (row, data) in enumerate(valid):
                        try:
                            vector = vectors[offset:offset + 1] if vectors is not None else embedder.embed([data])
                            current.add(vector, [Reference(int(row['landmark_id']), 'neon:' + row['id'])])
                            records.append({'id': row['id'], 'url': row['url'], 'landmark_id': row['landmark_id'], 'sha256': sha256(data).hexdigest()})
                            connection.execute("UPDATE images SET state='buffered' WHERE id=?", (row['id'],))
                        except Exception as error:
                            connection.execute("UPDATE images SET state='retry',attempts=attempts+1,next_attempt=?,error=? WHERE id=?", (time.time() + 3600, json.dumps({'type': type(error).__name__, 'reason': str(error)[:500]}), row['id']))
                connection.commit()
                if len(records) >= shard_size or (max_rows is not None and attempted >= max_rows):
                    commit_shard(connection, directory, current, records)
                    current = ReferenceIndex(embedder.dimension, embedder.signature)
                    records = []
                if time.monotonic() - last_status >= 30:
                    status(connection, directory, started)
                    last_status = time.monotonic()
                if max_rows is not None and attempted >= max_rows:
                    return status(connection, directory, started, 'pilot_stopped')
    finally:
        if 'connection' in locals():
            connection.close()
        lock.close()


def main():
    from dotenv import load_dotenv
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--model', default='dinov2-small')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--interval', type=float, default=.25)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--shard-size', type=int, default=1024)
    parser.add_argument('--max-rows', type=int)
    args = parser.parse_args()
    if min(args.batch_size, args.workers, args.threads, args.shard_size) < 1 or args.interval < 0:
        parser.error('Batch sizes, workers, threads and shard size must be positive')
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        parser.error('Set DATABASE_URL')
    run(args.directory, database_url, model=args.model, batch_size=args.batch_size,
        workers=args.workers, interval=args.interval, threads=args.threads,
        shard_size=args.shard_size, max_rows=args.max_rows)


if __name__ == '__main__':
    main()
