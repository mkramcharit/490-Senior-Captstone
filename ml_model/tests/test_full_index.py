import json
from types import SimpleNamespace
from urllib.error import HTTPError

import numpy as np

from landmark_ml import Reference, ReferenceIndex
from landmark_ml.full_index import image_url, open_ledger, put_meta, recover_shards, run


def seed(directory):
    directory.mkdir()
    connection = open_ledger(directory)
    rows = [('1', 'a', 104169), ('2', 'b', 25719), ('3', 'c', 25719), ('4', 'd', 73107)]
    connection.executemany('INSERT INTO images(id,url,landmark_id) VALUES (?,?,?)', rows)
    connection.commit()
    put_meta(connection, 'snapshot_complete', True)
    put_meta(connection, 'source_counts', {'rows': 4, 'landmarks': 3})
    connection.close()


def model():
    return SimpleNamespace(dimension=2, signature='test', embed=lambda data: np.array([[1, 0]] * len(data)))


def test_standard_thumbnail_url():
    assert image_url('http://upload.wikimedia.org/wikipedia/commons/a/ab/Example.jpg') == 'https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Example.jpg/500px-Example.jpg'
    assert image_url('https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Test.svg/960px-Test.svg.png').endswith('/500px-Test.svg.png')


def test_full_runner_retries_transient_failures_and_reports_real_coverage(tmp_path):
    directory = tmp_path / 'full'
    seed(directory)
    def download(url):
        if url == 'b':
            raise HTTPError(url, 429, 'rate limited', {}, None)
        if url == 'd':
            raise HTTPError(url, 404, 'gone', {}, None)
        return b'image'
    result = run(directory, 'postgresql://localhost/db', max_rows=4, batch_size=2, shard_size=2, embedder=model(), downloader=download)
    assert result['counts'] == {'indexed': 2, 'retry': 1, 'unavailable': 1}
    assert not (directory / 'bundle').exists()
    connection = open_ledger(directory)
    connection.execute('UPDATE images SET next_attempt=0')
    connection.commit()
    connection.close()
    result = run(directory, 'postgresql://localhost/db', embedder=model(), downloader=lambda url: b'image')
    assert result['counts'] == {'indexed': 3, 'unavailable': 1}
    restored = ReferenceIndex.load(directory / 'bundle', 'test')
    assert sorted(r.landmark_id for r in restored.references) == [25719, 25719, 104169]
    assert json.loads((directory / 'bundle/missing_landmark_ids.json').read_text()) == [73107]


def test_recover_committed_shard_before_reprocessing_buffered_rows(tmp_path):
    directory = tmp_path / 'full'
    seed(directory)
    index = ReferenceIndex(2, 'test')
    index.add([[1, 0]], [Reference(104169, 'neon:1')])
    shard = directory / 'shards/shard-recovery'
    index.save(shard)
    (shard / 'records.json').write_text(json.dumps([{'id': '1'}]))
    (shard / 'ready').write_text('ready')
    connection = open_ledger(directory)
    recover_shards(connection, directory)
    recover_shards(connection, directory)
    assert connection.execute("SELECT state,shard FROM images WHERE id='1'").fetchone()[:] == ('indexed', 'shard-recovery')
    connection.close()
