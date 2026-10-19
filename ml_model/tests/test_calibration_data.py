import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from landmark_ml import Reference, ReferenceIndex

script = Path(__file__).resolve().parents[2] / "scripts" / "calibrate_confidence.py"
spec = importlib.util.spec_from_file_location("calibrate_confidence", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def manifests(tmp_path):
    rng = np.random.default_rng(62)
    rows = []
    for i in range(41):
        path = tmp_path / f"{i}.png"
        Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(path)
        rows.append({"landmark_id": 1, "image_path": path.name})
    calibration = tmp_path / "calibration.json"
    test = tmp_path / "test.json"
    calibration.write_text(json.dumps(rows[1:21]))
    test.write_text(json.dumps(rows[21:]))
    return tmp_path / "0.png", calibration, test


def test_audit_accepts_disjoint_images(tmp_path):
    reference, calibration, test = manifests(tmp_path)
    sets = module.audit_images([reference], calibration, test)
    assert [len(rows) for rows in sets] == [20, 20]


def test_audit_rejects_test_calibration_overlap(tmp_path):
    reference, calibration, test = manifests(tmp_path)
    rows = json.loads(test.read_text())
    rows[0] = json.loads(calibration.read_text())[0]
    test.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="overlaps calibration"):
        module.audit_images([reference], calibration, test)


def test_audit_rejects_reference_reencoding(tmp_path):
    reference, calibration, test = manifests(tmp_path)
    copy = tmp_path / "reencoded.bmp"
    with Image.open(reference) as image:
        image.save(copy)
    rows = json.loads(calibration.read_text())
    rows[0]["image_path"] = copy.name
    calibration.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="overlaps reference"):
        module.audit_images([reference], calibration, test)


def test_audit_rejects_shared_source_event(tmp_path):
    reference, calibration, test = manifests(tmp_path)
    for manifest in (calibration, test):
        rows = json.loads(manifest.read_text())
        rows[0]["group_id"] = "same-photo-event"
        manifest.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="Source group overlaps"):
        module.audit_images([reference], calibration, test)


def test_batched_evaluation_preserves_outcomes_and_groups():
    index = ReferenceIndex(2, "test")
    index.add([[1, 0]], [Reference(1, "ref.png")])
    pipeline = SimpleNamespace(index=index, embedder=SimpleNamespace(embed=lambda paths: np.array([[1, 0]] * len(paths))))
    records = [{"path": Path(f"{i}.png"), "sha256": str(i), "group_id": "group" + str(i),
                "landmark_id": 1 if i % 2 else 99} for i in range(10)]
    results = module.evaluate_rows(pipeline, records, 5)
    assert len(results) == 10
    assert sum(r["correct"] for r in results) == 5
    assert results[9]["group_id"] == "group9"
    assert all(r["match_score"] == 1 for r in results)
