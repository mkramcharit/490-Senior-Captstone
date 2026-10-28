import json

import faiss
import numpy as np
import pytest

from landmark_ml import Reference, ReferenceIndex
from landmark_ml.compact import approximation_report, validate_master
from landmark_ml.full_index import open_ledger
from test_full_index import seed


def test_quantized_index_loads_through_existing_pipeline_format(tmp_path):
    faiss.omp_set_num_threads(2)
    rng = np.random.default_rng(7)
    vectors = rng.normal(size=(1024, 8)).astype('float32')
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    compact = faiss.IndexPQ(8, 2, 4, faiss.METRIC_INNER_PRODUCT)
    compact.train(vectors)
    compact.add(vectors[:64])
    index = ReferenceIndex(8, 'test')
    index.index = compact
    index.references = [Reference(i // 4, f'neon:{i}') for i in range(64)]
    index._paths = {r.image_path for r in index.references}
    index.save(tmp_path / 'bundle')
    restored = ReferenceIndex.load(tmp_path / 'bundle', 'test')
    assert restored.predict(vectors[2]) == index.predict(vectors[2])
    assert restored.index.ntotal == 64


def test_approximation_comparison_excludes_query_self():
    index = ReferenceIndex(2, 'test')
    index.add([[1, 0], [.8, .6], [.6, .8]], [Reference(1, 'a'), Reference(2, 'b'), Reference(3, 'c')])
    query = np.array([[1, 0]], dtype='float32')
    scores, positions = index.index.search(query, 3)
    report = approximation_report(index, index.index, query, [0], scores, positions)
    assert report['neighbor_recall_at_10'] == 1
    assert report['landmark_decision_agreement'] == 1


def test_master_verification_checks_original_neon_mapping(tmp_path):
    directory = tmp_path / 'full'
    seed(directory)
    connection = open_ledger(directory)
    connection.execute("UPDATE images SET state='indexed'")
    connection.commit()
    connection.close()
    index = ReferenceIndex(2, 'test')
    labels = [104169, 25719, 25719, 73107]
    index.add([[1, 0]] * 4, [Reference(label, f'neon:{i+1}') for i, label in enumerate(labels)])
    assert validate_master(index, directory)['all_source_rows_accounted_for']
    index.references[0] = Reference(999, 'neon:1')
    with pytest.raises(ValueError, match='Neon label'):
        validate_master(index, directory)
