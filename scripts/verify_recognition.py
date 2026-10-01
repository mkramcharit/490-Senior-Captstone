import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.app import app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("holdouts", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.holdouts.read_text(encoding="utf-8"))
    if not rows:
        parser.error("No held-out images supplied")
    from backend.app import configured_path
    index_directory = configured_path("LANDMARK_INDEX_PATH", "artifacts/landmarks")
    mapping = json.loads((index_directory / "references.json").read_text(encoding="utf-8"))
    reference_hashes = {hashlib.sha256(Path(row["image_path"]).read_bytes()).hexdigest()
                        for row in mapping["references"]}
    results = []
    with TestClient(app) as client:
        for row in rows:
            path = args.holdouts.parent / row["image_path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() in reference_hashes:
                parser.error(f"Held-out photo is also in the reference index: {path.name}")
            response = client.post("/api/predict", files={"image": (path.name, path.read_bytes(), "image/jpeg")})
            payload = response.json()
            correct = response.status_code == 200 and payload.get("landmark_id") == row["landmark_id"]
            result = {"image_path": row["image_path"], "expected_landmark_id": row["landmark_id"],
                      "status": response.status_code, "correct": correct, "response": payload}
            results.append(result)
            print(json.dumps(result), flush=True)
    report = {"evaluation": "held-out images through real FastAPI endpoint and Neon lookup",
              "correct": sum(row["correct"] for row in results), "total": len(results), "results": results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not all(row["correct"] for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
