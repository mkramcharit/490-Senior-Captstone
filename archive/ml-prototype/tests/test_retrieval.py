import json

import numpy as np
import pytest

from landmark_ml import Reference, ReferenceIndex

def make_index(scores, ids):
    index = ReferenceIndex(2, "test-model")
    vectors = [[score, np.sqrt(1 - score**2)] for score in scores]
    index.add(vectors, [Reference(key, f"{i}.jpg") for i, key in enumerate(ids)])
    return index

def test_cosine_search():
    index = ReferenceIndex(2, "test-model")
    index.add([[10, 0], [0, 7]], [Reference(417, "a"), Reference(883, "b")])
    result = index.predict([3, 0], top_k=100)
    assert result["landmark_id"] == 417
    assert result["similarity"] == pytest.approx(1)
    assert len(result["top_matches"]) == 2
    assert result["confidence"] == pytest.approx(0.5)

def test_match_agreement():
    agreeing = make_index([0.94, 0.92, 0.90], [417, 417, 417]).predict([1, 0])
    mixed = make_index([0.94, 0.92, 0.90], [417, 883, 417]).predict([1, 0])
    assert agreeing["confidence"] == pytest.approx(0.94)
    assert mixed["confidence"] < agreeing["confidence"]
    assert mixed["landmark_id"] == 417

def test_landmark_voting():
    result = make_index([0.95, 0.92, 0.91], [883, 417, 417]).predict([1, 0])
    assert result["landmark_id"] == 417
    assert result["similarity"] == pytest.approx(0.92)

def test_weak_matches():
    result = make_index([0.05, 0.04, 0.03], [417] * 3).predict([1, 0])
    assert result["confidence"] == pytest.approx(0.05)
    result = make_index([-0.1, -0.2], [417, 417]).predict([1, 0])
    assert result["confidence"] == 0

def test_index_storage(tmp_path):
    index = make_index([0.94, 0.92, 0.7], [417, 417, "louvre"])
    target = tmp_path / "index"
    index.save(target)
    restored = ReferenceIndex.load(target, "test-model")
    assert restored.predict([1, 0]) == index.predict([1, 0])
    with pytest.raises(ValueError, match="differs"):
        ReferenceIndex.load(target, "other-model")
    with pytest.raises(FileExistsError):
        index.save(target)
    mapping = target / "references.json"
    data = json.loads(mapping.read_text())
    data["references"].pop()
    mapping.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="counts"):
        ReferenceIndex.load(target, "test-model")

@pytest.mark.parametrize("vector", [[0, 0], [float("nan"), 1], [float("inf"), 1], [1, 2, 3]])
def test_invalid_vectors(vector):
    index = make_index([1.0], [417])
    with pytest.raises(ValueError):
        index.predict(vector)

def test_invalid_inputs():
    index = ReferenceIndex(2, "test")
    with pytest.raises(ValueError, match="empty"):
        index.predict([1, 0])
    with pytest.raises(ValueError):
        index.add([[1,0]], [Reference(417, "a")])
    assert index.index.ntotal == 1
    for k in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            index.predict([1, 0], k)
