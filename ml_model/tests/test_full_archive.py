import io
import json
import tarfile

import pytest

from landmark_ml.full_archive import ArchiveReader, process_archive
from landmark_ml.full_index import open_ledger
from test_full_index import model, seed


def archive_bytes():
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        for key in ['1', '2', '99', '3', '4']:
            item = tarfile.TarInfo(key + '.jpg')
            item.size = 5
            archive.addfile(item, io.BytesIO(b'image'))
    return output.getvalue()


def test_archives_only_index_neon_ids_and_preserve_neon_labels(tmp_path, monkeypatch):
    directory = tmp_path / 'full'
    seed(directory)
    connection = open_ledger(directory)
    connection.execute('CREATE TABLE archives (number INTEGER PRIMARY KEY, offset INTEGER, complete INTEGER)')
    data = archive_bytes()
    monkeypatch.setattr('landmark_ml.full_archive.stream_archive', lambda number, offset: io.BytesIO(data[offset:]))
    process_archive(connection, directory, 0, model(), batch_size=2, shard_size=2)
    assert dict(connection.execute('SELECT state,count(*) FROM images GROUP BY state')) == {'indexed': 4}
    assert connection.execute('SELECT complete FROM archives WHERE number=0').fetchone()[0] == 1
    records = []
    for path in (directory / 'shards').glob('*/records.json'):
        records.extend(json.loads(path.read_text()))
    assert sorted(r['id'] for r in records) == ['1', '2', '3', '4']
    assert sorted(r['landmark_id'] for r in records) == [25719, 25719, 73107, 104169]
    process_archive(connection, directory, 0, model(), batch_size=2, shard_size=2)
    assert connection.execute("SELECT count(*) FROM images WHERE state='indexed'").fetchone()[0] == 4
    connection.close()


def test_archive_reader_detects_truncated_network_body():
    response = io.BytesIO(b'abc')
    response.headers = {'Content-Length': '6'}
    reader = ArchiveReader(response)
    with pytest.raises(EOFError):
        reader.verify_complete()
