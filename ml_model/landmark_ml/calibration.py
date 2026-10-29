import hashlib
import json
from pathlib import Path

import faiss
import numpy as np


def index_signature(index):
    digest = hashlib.sha256(faiss.serialize_index(index.index).tobytes())
    digest.update(json.dumps([r.landmark_id for r in index.references]).encode())
    digest.update(index.signature.encode())
    return digest.hexdigest()


def sigmoid(values):
    return 1 / (1 + np.exp(-np.clip(values, -40, 40)))


def fit(scores, correct):
    scores, correct = np.asarray(scores, dtype=float), np.asarray(correct, dtype=float)
    if scores.ndim != 1 or scores.shape != correct.shape or len(scores) < 20:
        raise ValueError("Use at least 20 separate calibration photos")
    if not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
        raise ValueError("Scores must be finite and within [0, 1]")
    if not np.isin(correct, [0, 1]).all() or min(sum(correct == 0), sum(correct == 1)) < 5:
        raise ValueError("Calibration requires at least five correct and five incorrect predictions")
    mean, scale = float(scores.mean()), float(scores.std())
    if scale < 1e-8:
        raise ValueError("Calibration scores have no variation")
    design = np.column_stack([np.ones(len(scores)), (scores - mean) / scale])
    weights = np.array([np.log(correct.mean() / (1 - correct.mean())), 0.0])
    penalty = np.diag([0.0, 1.0])
    for _ in range(100):
        probabilities = sigmoid(design @ weights)
        gradient = design.T @ (probabilities - correct) + penalty @ weights
        hessian = design.T @ ((probabilities * (1 - probabilities))[:, None] * design) + penalty
        step = np.linalg.solve(hessian + np.eye(2) * 1e-8, gradient)
        weights -= step
        if np.linalg.norm(step) < 1e-8:
            break
    return {"version": 1, "method": "regularized_sigmoid", "mean": mean, "scale": scale,
            "weights": weights.tolist(), "sample_count": len(scores),
            "correct_count": int(correct.sum()), "score_range": [float(scores.min()), float(scores.max())]}


def probability(model, score):
    if model.get('method', 'regularized_sigmoid') == 'regularized_logistic_features':
        from .confidence_features import feature_probability
        return feature_probability(model, score)
    if isinstance(score, dict):
        score = score['match_score']
    return float(sigmoid(model["weights"][0] + model["weights"][1] * (score - model["mean"]) / model["scale"]))


def load(path, index):
    model = json.loads(Path(path).read_text(encoding="utf-8"))
    if model.get("version") not in (1, 2) or model.get("method") not in ('regularized_sigmoid','regularized_logistic_features'):
        raise ValueError("Unsupported calibration format")
    if model['version'] == 2:
        if (model.get('deployment_status') != 'approved' or not isinstance(model.get('validation_scope'), str)
                or not model['validation_scope'].strip() or type(model.get('validation_sample_count')) is not int
                or model['validation_sample_count'] < 100 or 'validated_probability_range' not in model):
            raise ValueError('Validated calibration metadata is missing or insufficient')
        digest = model.get('validation_report_sha256', '')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid calibration validation report identity')
    if model.get('deployment_status') not in (None, 'approved'):
        raise ValueError('Calibration is an evaluation candidate and is not approved for runtime use')
    if model.get("index_signature") != index_signature(index):
        raise ValueError("Calibration does not match the current index and model")
    if model['method'] == 'regularized_logistic_features':
        from .confidence_features import FEATURES
        parameters = [*model['feature_mean'],*model['feature_scale'],*model['weights']]
        if (model.get('features') != FEATURES or len(model['feature_mean']) != len(FEATURES)
                or len(model['feature_scale']) != len(FEATURES) or len(model['weights']) != len(FEATURES)+1
                or not np.isfinite(parameters).all() or any(value<=0 for value in model['feature_scale'])):
            raise ValueError('Invalid feature calibration parameters')
    else:
        parameters = [model["mean"], model["scale"], *model["weights"]]
        if len(model["weights"]) != 2 or not np.isfinite(parameters).all() or model["scale"] <= 0:
            raise ValueError("Invalid calibration parameters")
    if type(model.get("top_k")) is not int or model["top_k"] < 1:
        raise ValueError("Invalid calibration search configuration")
    for field in ('score_range', 'validated_probability_range'):
        if field in model:
            bounds = model[field]
            if not isinstance(bounds, list) or len(bounds) != 2 or not np.isfinite(bounds).all() or not 0 <= bounds[0] <= bounds[1] <= 1:
                raise ValueError(f'Invalid calibration {field}')
    if model.get('population', 'all_candidates') not in ('all_candidates', 'accepted_predictions'):
        raise ValueError('Unsupported calibration population')
    if 'recognition_policy' in model:
        from .decision import RecognitionPolicy
        RecognitionPolicy(**model['recognition_policy'])
    return model


def metrics(probabilities, correct, bins=5):
    if type(bins) is not int or bins < 1:
        raise ValueError('Reliability bins must be a positive integer')
    probabilities, correct = np.asarray(probabilities, dtype=float), np.asarray(correct, dtype=float)
    if not len(probabilities) or probabilities.shape != correct.shape:
        raise ValueError("Evaluation requires paired probabilities and outcomes")
    if (not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any()
            or not np.isin(correct, [0, 1]).all()):
        raise ValueError("Invalid evaluation data")
    reliability, ece = [], 0.0
    for i in range(bins):
        selected = (probabilities >= i / bins) & ((probabilities < (i + 1) / bins) if i < bins - 1 else (probabilities <= 1))
        count = int(selected.sum())
        if not count:
            continue
        observed, predicted = float(correct[selected].mean()), float(probabilities[selected].mean())
        z = 1.96
        center = (observed + z*z/(2*count)) / (1 + z*z/count)
        half = z * np.sqrt(observed*(1-observed)/count + z*z/(4*count*count)) / (1 + z*z/count)
        reliability.append({"lower": i / bins, "upper": (i + 1) / bins, "count": count,
                            "mean_probability": predicted, "observed_accuracy": observed,
                            "accuracy_interval_95": [float(center-half), float(center+half)]})
        ece += count / len(correct) * abs(observed - predicted)
    clipped = np.clip(probabilities, 1e-12, 1 - 1e-12)
    return {"sample_count": len(correct), "accuracy": float(correct.mean()),
            "brier_score": float(np.mean((probabilities-correct)**2)),
            "log_loss": float(-np.mean(correct*np.log(clipped)+(1-correct)*np.log(1-clipped))),
            "expected_calibration_error": ece, "reliability_bins": reliability}
