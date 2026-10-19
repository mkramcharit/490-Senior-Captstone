import pickle
from types import SimpleNamespace

import numpy as np
import pytest

from landmark_ml import LandmarkPipeline, Reference, ReferenceIndex, recognize_image
from landmark_ml.indexing import export_index, fetch_rows, merge_shards, process_rows


def embedder():
    def embed(images):
        if any(image == b'broken' for image in images):
            raise ValueError('bad image')
        return np.array([[1, 0] if image == b'a' else [0, 1] for image in images])
    return SimpleNamespace(dimension=2, signature='test', embed=embed)


def test_download_and_embedding_failures_keep_mapping_aligned(tmp_path):
    rows = [{'id': str(i), 'url': str(i), 'landmark_id': 100 + i} for i in range(4)]
    def download(url):
        if url == '1':
            raise OSError('unavailable')
        return {'0': b'a', '2': b'broken', '3': b'b'}[url]
    index, failures = process_rows(rows, embedder(), 4, 2, download)
    assert [r.landmark_id for r in index.references] == [100, 103]
    assert {f['id'] for f in failures} == {'1', '2'}
    assert index.predict([0, 1], top_k=1)['landmark_id'] == 103
    output = tmp_path / 'bundle'
    export_index(index, output)
    with (output / 'landmark_ids.pkl').open('rb') as stream:
        assert pickle.load(stream) == [100, 103]
    assert (output / 'landmarks.index').read_bytes() == (output / 'images.faiss').read_bytes()
    restored = ReferenceIndex.load(output, 'test')
    assert restored.predict([0, 1], top_k=1)['landmark_id'] == 103


def test_shards_preserve_order_and_multiple_photos_per_landmark(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    for i in range(2):
        index = ReferenceIndex(2, 'test')
        index.add([[1, 0]], [Reference(104169, 'neon:' + str(i))])
        index.save(work / f'batch-{i:09d}')
    result = merge_shards(work, embedder(), tmp_path / 'final')
    assert [r.landmark_id for r in result.references] == [104169, 104169]
    assert result.index.ntotal == 2
    with pytest.raises(ValueError, match='Duplicate'):
        result.add([[1, 0]], [Reference(1, 'neon:0')])


def test_keyset_query_is_bounded_and_parameterized():
    class Connection:
        def execute(self, query, parameters):
            self.query, self.parameters = query, parameters
            return SimpleNamespace(fetchall=lambda: [])
    connection = Connection()
    assert fetch_rows(connection, 'last', 256, [25719]) == []
    assert 'id > %s' in connection.query
    assert 'ORDER BY id LIMIT %s' in connection.query
    assert connection.parameters == ['last', [25719], 256]


def test_compatibility_confidence_and_tuple_adapter(monkeypatch):
    index = ReferenceIndex(2, 'test')
    index.add([[1, 0]], [Reference(25719, 'neon:1')])
    pipeline = LandmarkPipeline(embedder(), index)
    result = pipeline.predict(b'a')
    assert result['confidence'] == result['match_score'] == 1
    monkeypatch.setattr('landmark_ml.recognition._pipeline', lambda *args: pipeline)
    assert recognize_image(b'a') == (25719, 1.0)
    pipeline.calibrator = {'top_k': 5, 'mean': 0, 'scale': 1, 'weights': [0, 0]}
    assert recognize_image(b'a') == (25719, .5)
    assert pipeline.predict(b'a')['confidence_calibrated']


def test_interrupted_build_resumes_without_reindexing_committed_rows(tmp_path, monkeypatch):
    import landmark_ml.indexing as indexing
    import psycopg
    source = [{'id': str(i), 'url': str(i), 'landmark_id': 100 + i} for i in range(3)]
    interrupted = [False]
    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, parameters=None):
            if parameters is None:
                return None
            after = parameters[0] if len(parameters) > 1 else None
            if after == '1' and not interrupted[0]:
                interrupted[0] = True
                raise OSError('interrupted connection')
            rows = [r for r in source if after is None or r['id'] > after]
            return SimpleNamespace(fetchall=lambda: rows[:parameters[-1]])
    monkeypatch.setattr(psycopg, 'connect', lambda *args, **kwargs: Connection())
    monkeypatch.setattr(indexing, 'DinoV2Embedder', lambda *args: embedder())
    real_process = indexing.process_rows
    seen = []
    def process(rows, model, batch_size, workers):
        seen.extend(r['id'] for r in rows)
        return real_process(rows, model, batch_size, workers, lambda url: b'a')
    monkeypatch.setattr(indexing, 'process_rows', process)
    output = tmp_path / 'index'
    with pytest.raises(OSError, match='interrupted'):
        indexing.build_from_neon(output, fetch_size=2, database_url='postgresql://host/db')
    report = indexing.build_from_neon(output, fetch_size=2, resume=True, database_url='postgresql://host/db')
    assert seen == ['0', '1', '2']
    assert report['processed_rows'] == report['indexed_images'] == 3
    assert [r.landmark_id for r in ReferenceIndex.load(output, 'test').references] == [100, 101, 102]
