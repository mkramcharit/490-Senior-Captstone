import argparse
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "trekmark-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.evaluation.read_text(encoding="utf-8"))
    rows = report["test_results"]
    calibrated = report["calibrated_probability"]
    raw = report["raw_match_score_as_probability"]
    constant = report["constant_calibration_accuracy_baseline"]
    y = np.array([r["correct"] for r in rows], dtype=float)
    probabilities = np.array([r["confidence_probability"] for r in rows])
    scores = np.array([r["match_score"] for r in rows])
    difference = (probabilities-y)**2 - (scores-y)**2
    rng = np.random.default_rng(20261003)
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(row.get("group_id", row["sha256"]), []).append(i)
    clusters = list(groups.values())
    bootstrap = np.array([difference[np.concatenate([clusters[i] for i in rng.integers(0, len(clusters), len(clusters))])].mean() for _ in range(2000)])
    interval = np.quantile(bootstrap, [.025, .975]).tolist()
    bins = calibrated["reliability_bins"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    axes[0].plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    x, observed = [b["mean_probability"] for b in bins], [b["observed_accuracy"] for b in bins]
    errors = np.array([[b["observed_accuracy"]-b["accuracy_interval_95"][0] for b in bins],
                       [b["accuracy_interval_95"][1]-b["observed_accuracy"] for b in bins]])
    axes[0].errorbar(x, observed, yerr=np.maximum(0, errors), fmt="o", capsize=4, color="#166c8c", label="Test bins; 95% Wilson intervals")
    for predicted, accuracy, b in zip(x, observed, bins):
        axes[0].annotate(f"n={b['count']}", (predicted, accuracy), xytext=(5, 7), textcoords="offset points", fontsize=9)
    axes[0].set(xlim=(-.03, 1.03), ylim=(-.03, 1.03), xlabel="Mean predicted probability", ylabel="Observed correctness", title="Reliability on independent test photos")
    axes[0].legend(fontsize=8, loc="lower right")
    axes[1].bar(["Raw score", "Calibrated", "Constant\nbaseline"], [raw["brier_score"], calibrated["brier_score"], constant["brier_score"]], color=["#999999", "#166c8c", "#d9a441"])
    axes[1].set(ylabel="Brier score (lower is better)", title="Probability prediction error")
    indexed_ids = set(report["indexed_landmark_ids"])
    tested_ids = {str(r["expected_landmark_id"]) for r in rows}
    fig.suptitle(f"{len(tested_ids & indexed_ids)} indexed + {len(tested_ids - indexed_ids)} unindexed landmarks tested | {len(rows)} test / {report['calibration_sample_count']} calibration photos", fontsize=11)
    fig.tight_layout()
    args.output.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output / "reliability.png", dpi=180)
    fig.savefig(args.output / "reliability.pdf")
    plt.close(fig)
    per_landmark = {}
    for key in sorted({str(r["expected_landmark_id"]) for r in rows}):
        group = [r for r in rows if str(r["expected_landmark_id"]) == key]
        per_landmark[key] = {"count": len(group), "correct": sum(r["correct"] for r in group),
                             "mean_probability": float(np.mean([r["confidence_probability"] for r in group]))}
    promising = len(rows) >= 50 and calibrated["expected_calibration_error"] <= .10 and calibrated["brier_score"] < raw["brier_score"]
    summary = {"sample_count": len(rows), "accuracy": calibrated["accuracy"],
               "source_group_count": len(clusters),
               "indexed_landmark_ids": sorted(indexed_ids), "tested_landmark_ids": sorted(tested_ids),
               "mean_probability": float(probabilities.mean()), "expected_calibration_error": calibrated["expected_calibration_error"],
               "raw_brier": raw["brier_score"], "calibrated_brier": calibrated["brier_score"], "constant_baseline_brier": constant["brier_score"],
               "calibrated_minus_raw_brier_bootstrap_interval_95": interval,
               "meets_predeclared_descriptive_checks": promising, "per_landmark": per_landmark,
               "scope": "Neon-labeled Wikimedia benchmark with selected indexed and unindexed landmarks; not arbitrary uploads"}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
