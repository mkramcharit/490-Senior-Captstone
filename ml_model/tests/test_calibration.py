import json
from types import SimpleNamespace

import numpy as np
import pytest

from landmark_ml import Reference, ReferenceIndex, LandmarkPipeline
from landmark_ml.calibration import fit, index_signature, load, metrics, probability


def calibration_sample():
    rng = np.random.default_rng(21)
    scores = rng.uniform(0, 1, 1000)
    outcomes = rng.random(len(scores)) < (1 / (1 + np.exp(-(8 * scores - 4))))
    return scores, outcomes


def test_sigmoid_learns_correctness_on_independent_samples():
    scores, outcomes = calibration_sample()
    model = fit(scores[:600], outcomes[:600])
    predictions = [probability(model, score) for score in scores[600:]]
    report = metrics(predictions, outcomes[600:])
    baseline = metrics([float(outcomes[:600].mean())] * 400, outcomes[600:])
    assert report["brier_score"] < baseline["brier_score"] - 0.05
    assert probability(model, 0.9) > probability(model, 0.1)
    assert sum(r["count"] for r in report["reliability_bins"]) == 400


def test_reliability_includes_boundaries_and_uncertainty():
    report = metrics([0, 1, .5, .5], [0, 1, 0, 1])
    assert report["brier_score"] == pytest.approx(.125)
    assert report["expected_calibration_error"] == 0
    assert sum(b["count"] for b in report["reliability_bins"]) == 4
    assert all(0 <= b["accuracy_interval_95"][0] <= b["accuracy_interval_95"][1] <= 1 + 1e-12 for b in report["reliability_bins"])


@pytest.mark.parametrize("scores,outcomes", [([.1]*5, [0]*5), ([.1]*20, [0]*20),
                                             ([float("nan")]*20, [0, 1]*10), ([.1]*20, [0, 1]*10)])
def test_rejects_insufficient_or_invalid_calibration(scores, outcomes):
    with pytest.raises(ValueError):
        fit(scores, outcomes)


def test_calibrator_bound_to_index_labels_vectors_and_top_k(tmp_path, monkeypatch):
    index = ReferenceIndex(2, "test")
    index.add([[1, 0], [0, 1]], [Reference(1, "a.jpg"), Reference(2, "b.jpg")])
    directory = tmp_path / "index"
    index.save(directory)
    scores, outcomes = calibration_sample()
    model = fit(scores, outcomes)
    model.update(index_signature=index_signature(index), top_k=5)
    path = directory / "calibration.json"
    path.write_text(json.dumps(model))
    embedder = SimpleNamespace(signature="test", dimension=2, embed=lambda images: np.array([[1, 0]]))
    monkeypatch.setattr("landmark_ml.pipeline.DinoV2Embedder", lambda *args: embedder)
    pipeline = LandmarkPipeline.load(directory)
    prediction = pipeline.predict(b"test")
    assert prediction["confidence_calibrated"]
    assert prediction["confidence_probability"] == pytest.approx(probability(model, .5))
    assert pipeline.predict(b"test", top_k=1)["confidence_probability"] is None
    index.references[0] = Reference(3, "a.jpg")
    with pytest.raises(ValueError, match="does not match"):
        load(path, index)


def test_uncalibrated_prediction_has_no_probability():
    index = ReferenceIndex(2, "test")
    index.add([[1, 0]], [Reference(1, "a.jpg")])
    result = index.predict([1, 0])
    assert result["match_score"] == 1
    assert result["confidence_probability"] is None
    assert not result["confidence_calibrated"]
