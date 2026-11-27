from types import SimpleNamespace

import numpy as np
import pytest

from landmark_ml import LandmarkPipeline, Reference, ReferenceIndex
from landmark_ml.decision import RecognitionPolicy


def pipeline(scores, labels):
    index = ReferenceIndex(2, 'test')
    index.add([[score, np.sqrt(1-score**2)] for score in scores], [Reference(label, f'neon:{i}') for i, label in enumerate(labels)])
    embedder = SimpleNamespace(signature='test', dimension=2, embed=lambda images: np.array([[1, 0]]))
    return LandmarkPipeline(embedder, index)


def test_japan_failure_evidence_is_rejected_instead_of_returning_china():
    result = pipeline([.779718, .754598, .752237, .750941, .745122], [141527, 46066, 4545, 173673, 202854]).predict(b'image')
    assert result['landmark_id'] is None
    assert result['candidate_landmark_id'] == 141527
    assert result['prediction_status'] == 'unknown'
    assert result['confidence'] is None
    assert len(result['top_matches']) == 5


def test_distinct_consensus_can_pass_without_inventing_probability():
    result = pipeline([.91, .90, .70, .68, .65], [1, 1, 2, 3, 4]).predict(b'image')
    assert result['landmark_id'] == 1
    assert result['prediction_status'] == 'candidate'
    assert result['confidence'] is None


def test_strong_but_conflicting_landmarks_are_rejected():
    result = pipeline([.94, .935, .93, .92, .91], [1, 2, 1, 2, 3]).predict(b'image')
    assert result['landmark_id'] is None


def test_weak_consensus_is_rejected():
    assert pipeline([.60, .59, .58], [1, 1, 1]).predict(b'image')['landmark_id'] is None


def test_near_duplicate_with_clear_margin_preserves_exact_match():
    assert pipeline([.997, .78, .77], [1, 2, 3]).predict(b'image')['landmark_id'] == 1


def test_tuple_adapter_preserves_unknown(monkeypatch):
    from landmark_ml import recognize_image
    monkeypatch.setattr('landmark_ml.recognition._pipeline', lambda *args: pipeline([.7, .69], [1, 2]))
    assert recognize_image(b'image') == (None, None)


@pytest.mark.parametrize('kwargs', [{'minimum_similarity': float('nan')}, {'minimum_support': 1}, {'minimum_margin': -1}])
def test_policy_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        RecognitionPolicy(**kwargs)
