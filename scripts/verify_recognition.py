import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.app import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("holdouts", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument('--index', type=Path)
    args = parser.parse_args()
    rows = json.loads(args.holdouts.read_text(encoding="utf-8"))
    if not rows:
        parser.error("No held-out images supplied")
    from landmark_ml.config import resolve_index
    index_directory = resolve_index(args.index)
    os.environ['LANDMARK_INDEX_PATH'] = str(index_directory)
    from backend.app import get_pipeline
    get_pipeline.cache_clear()
    mapping = json.loads((index_directory / "references.json").read_text(encoding="utf-8"))
    local_references = [Path(row['image_path']) for row in mapping['references'] if Path(row['image_path']).is_file()]
    reference_paths = {row['image_path'] for row in mapping['references']}
    reference_hashes = {hashlib.sha256(path.read_bytes()).hexdigest() for path in local_references}
    calibration_file = index_directory / "calibration.json"
    calibration_hashes = set()
    if calibration_file.is_file():
        calibration_hashes = set(json.loads(calibration_file.read_text(encoding="utf-8"))["calibration_image_hashes"])
    results = []
    with TestClient(app) as client:
        for row in rows:
            path = args.holdouts.parent / row["image_path"]
            if 'neon:' + path.stem in reference_paths or str(path.resolve()) in reference_paths:
                parser.error(f'Held-out photo ID is already indexed: {path.name}')
            if hashlib.sha256(path.read_bytes()).hexdigest() in reference_hashes | calibration_hashes:
                parser.error(f"Held-out photo overlaps reference or calibration data: {path.name}")
            response = client.post("/api/predict", files={"image": (path.name, path.read_bytes(), "image/jpeg")})
            payload = response.json()
            correct = response.status_code == 200 and payload.get("landmark_id") == row["landmark_id"]
            result = {"image_path": row["image_path"], "expected_landmark_id": row["landmark_id"],
                      "status": response.status_code, "correct": correct, "response": payload}
            results.append(result)
            print(json.dumps(result), flush=True)
    report = {"evaluation": "held-out images through real FastAPI endpoint and Neon lookup",
              "correct": sum(row["correct"] for row in results), "total": len(results), "results": results,
              'reference_content_audited': len(local_references) == len(mapping['references']),
              'limitations': 'Reference IDs and available local content are checked. Neon-ID references without local photos cannot be exhaustively checked for visual duplicates.'}
    scored = [r for r in results if r["status"] == 200 and r["response"].get("confidence_probability") is not None]
    if scored:
        from landmark_ml.calibration import metrics
        report["calibration_metrics"] = metrics([r["response"]["confidence_probability"] for r in scored], [r["correct"] for r in scored])
    report["calibrated_prediction_count"] = len(scored)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not all(row["correct"] for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
