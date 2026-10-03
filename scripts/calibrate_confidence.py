import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml_model"))
from landmark_ml import LandmarkPipeline
from landmark_ml.calibration import fit, index_signature, metrics, probability


def fingerprints(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("L").resize((9, 8))
        pixels = np.asarray(image)
        bits = (pixels[:, 1:] > pixels[:, :-1]).ravel()
    return digest, int.from_bytes(np.packbits(bits).tobytes(), "big")


def audit_images(reference_paths, calibration_manifest, test_manifest):
    seen = []
    for path in reference_paths:
        digest, visual = fingerprints(path)
        seen.append((digest, visual, "reference"))
    sets = []
    source_groups = {}
    for manifest, split in ((calibration_manifest, "calibration"), (test_manifest, "test")):
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or len(rows) < 20:
            raise ValueError(f"{split}: use at least 20 labeled photoss")
        records = []
        for row in rows:
            group = row.get("group_id")
            if group is not None:
                if group in source_groups and source_groups[group] != split:
                    raise ValueError(f"Source group overlaps calibration and test: {group}")
                source_groups[group] = split
            label = row["landmark_id"]
            if label is not None and (isinstance(label, bool) or not isinstance(label, (int, str))):
                raise ValueError("landmark_id must be an integer/string or null for unknown images")
            path = (manifest.parent / row["image_path"]).resolve()
            digest, visual = fingerprints(path)
            for previous_digest, previous_visual, previous_split in seen:
                if digest == previous_digest or (visual ^ previous_visual).bit_count() <= 4:
                    raise ValueError(f"Duplicate or visually near-duplicate photo in {split} overlaps {previous_split}: {path}")
            seen.append((digest, visual, split))
            records.append({"path": path, "landmark_id": label, "sha256": digest, "group_id": group or digest})
        sets.append(records)
    return sets


def evaluate_rows(pipeline, records, top_k):
    results = []
    for start in range(0, len(records), 8):
        batch = records[start:start + 8]
        vectors = pipeline.embedder.embed([row["path"] for row in batch])
        for row, vector in zip(batch, vectors):
            prediction = pipeline.index.predict(vector, top_k)
            correct = row["landmark_id"] is not None and str(prediction["landmark_id"]) == str(row["landmark_id"])
            results.append({"image_path": str(row["path"]), "sha256": row["sha256"],
                            "group_id": row["group_id"],
                            "expected_landmark_id": row["landmark_id"], "predicted_landmark_id": prediction["landmark_id"],
                            "match_score": prediction["match_score"], "correct": correct})
            print(f"{row['path'].name}: {'correct' if correct else 'incorrect'}", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("calibration_manifest", type=Path)
    parser.add_argument("test_manifest", type=Path)
    parser.add_argument("output", type=Path, help="New directory for calibration.json and evaluation.json")
    parser.add_argument("--model", default="dinov2-small")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.output.exists() or args.top_k < 1:
        parser.error("Choose a new output directory and positive top-k")
    pipeline = LandmarkPipeline.load(args.index, args.model)
    pipeline.calibrator = None
    calibration_rows, test_rows = audit_images(
        [Path(row.image_path) for row in pipeline.index.references], args.calibration_manifest, args.test_manifest)
    calibration_results = evaluate_rows(pipeline, calibration_rows, args.top_k)
    model = fit([r["match_score"] for r in calibration_results], [r["correct"] for r in calibration_results])
    model.update(index_signature=index_signature(pipeline.index), top_k=args.top_k,
                 calibration_image_hashes=[r["sha256"] for r in calibration_results],
                 calibration_manifest_sha256=hashlib.sha256(args.calibration_manifest.read_bytes()).hexdigest())
    test_results = evaluate_rows(pipeline, test_rows, args.top_k)
    for row in test_results:
        row["confidence_probability"] = probability(model, row["match_score"])
    outcomes = [r["correct"] for r in test_results]
    report = {"evaluation": "independent top-label correctness calibration test",
              "index_signature": model["index_signature"], "top_k": args.top_k,
              "indexed_landmark_ids": sorted({str(r.landmark_id) for r in pipeline.index.references}),
              "calibration_manifest_sha256": model["calibration_manifest_sha256"],
              "test_manifest_sha256": hashlib.sha256(args.test_manifest.read_bytes()).hexdigest(),
              "calibration_sample_count": len(calibration_results),
              "raw_match_score_as_probability": metrics([r["match_score"] for r in test_results], outcomes),
              "calibrated_probability": metrics([r["confidence_probability"] for r in test_results], outcomes),
              "constant_calibration_accuracy_baseline": metrics([model["correct_count"] / model["sample_count"]] * len(test_results), outcomes),
              "calibration_results": calibration_results, "test_results": test_results,
              "limitations": "Minimum sample checks aren't accurate"}
    args.output.mkdir(parents=True)
    (args.output / "calibration.json").write_text(json.dumps(model, indent=2), encoding="utf-8")
    (args.output / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["calibrated_probability"], indent=2))
    print("Review independent evaluation before copying calibration.json into the index directory.")


if __name__ == "__main__":
    main()
