from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import tempfile

import faiss
import numpy as np

@dataclass(frozen=True)
class Reference:
    landmark_id: int | str
    image_path: str

    def __post_init__(self):
        if type(self.landmark_id) not in (int, str) or self.landmark_id == "":
            raise ValueError("landmark_id must be an integer or nonempty string")
        if not isinstance(self.image_path, str) or not self.image_path.strip():
            raise ValueError("image_path must be a nonempty string")

def normalize(vectors, dimension: int) -> np.ndarray:
    array = np.array(vectors, dtype= np.float32, order="C", copy=True)
    if array.ndim != 2 or array.shape[1] != dimension or not len(array):
        raise ValueError(f"Expected nonempty embeddings with shape (N, {dimension})")
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if not np.isfinite(array).all() or not np.isfinite(norms).all() or (norms <= 0).any():
        raise ValueError("Embeddings must be finite and nonzero")
    return array / norms

class ReferenceIndex:
    def __init__(self, dimension: int, signature: str):
        if dimension <= 0 or not signature:
            raise ValueError("A positive dimension and model signature are required")
        self.index = faiss.IndexFlatIP(dimension)
        self.signature = signature
        self.references: list[Reference] = []
        self._paths = set()

    def add(self, vectors, references: list[Reference]):
        vectors = normalize(vectors, self.index.d)
        if len(vectors) != len (references):
            raise ValueError("Every embedding must have one reference")
        if not all(isinstance(ref, Reference) for ref in references):
            raise ValueError("References must be Reference objects")
        paths = [ref.image_path for ref in references]
        if len(set(paths)) != len(paths) or self._paths.intersection(paths):
            raise ValueError("Duplicate reference image paths")
        self.index.add(vectors)
        self.references.extend(references)
        self._paths.update(paths)

    def predict(self, vector, top_k: int = 5) -> dict:
        return self.predict_batch(np.asarray(vector).reshape(1, -1), top_k)[0]

    def predict_batch(self, vectors, top_k: int = 5) -> list[dict]:
        if type(top_k) is not int or top_k < 1:
            raise ValueError("Must be a positive integer")
        if not self.references:
            raise ValueError("Reference index is empty")
        queries = normalize(vectors, self.index.d)
        scores, positions = self.index.search(queries, min(top_k, self.index.ntotal))
        return [self._prediction(row_scores, row_positions) for row_scores, row_positions in zip(scores, positions)]

    def _prediction(self, scores, positions):
        if not np.isfinite(scores).all() or any(position < 0 or position >= len(self.references) for position in positions):
            raise ValueError("Reference search returned invalid neighbors")
        matches = [
            {"landmark_id": self.references[int(pos)].landmark_id,
             "score": float(np.clip(score, -1, 1)),
             "image_path": self.references[int(pos)].image_path}
             for score, pos in zip(scores, positions)
        ]
        groups = {}
        for match in matches:
            groups.setdefault(match["landmark_id"], []).append(match["score"])
        winner = max(groups, key=lambda key: (
            sum(max(0, s) for s in groups[key]), max(groups[key])
        ))
        similarity = max(groups[winner])
        agreement = len(groups[winner]) / len(matches)
        match_score = max(0.0, similarity) * agreement
        return {"landmark_id": winner, "match_score": match_score,
                "confidence_probability": None, "confidence_calibrated": False,
                "similarity": similarity, "agreement": agreement,
                "top_matches": matches}

    def save(self, directory: str | Path, extra_files=None):
        if not self.references:
            raise ValueError("Cannot save an empty index")
        directory = Path(directory)
        if directory.exists():
            raise FileExistsError(directory)
        directory.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=directory.name + ".pending-", dir=directory.parent))
        try:
            faiss.write_index(self.index, str(staging / "images.faiss"))
            payload = {"version": 1, "signature": self.signature,
                       "references": [asdict(ref) for ref in self.references]}
            (staging / "references.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            for name, content in (extra_files or {}).items():
                if name not in ('calibration.json', 'recognition-policy.json'):
                    raise ValueError('Unsupported runtime configuration filename')
                (staging / name).write_text(json.dumps(content, indent=2), encoding='utf-8')
            staging.rename(directory)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    @classmethod
    def load(cls, directory: str | Path, expected_signature: str):
        directory = Path(directory)
        payload = json.loads((directory / "references.json").read_text(encoding="utf-8"))
        if payload["version"] != 1 or payload["signature"] != expected_signature:
            raise ValueError("Index model does not match preprocessing")
        index = faiss.read_index(str(directory / "images.faiss"))
        if not isinstance(index, (faiss.IndexFlatIP, faiss.IndexPQ, faiss.IndexScalarQuantizer)) or index.metric_type != faiss.METRIC_INNER_PRODUCT or not index.is_trained:
            raise ValueError("Expected a supported inner product index")
        result = cls(index.d, expected_signature)
        result.index = index
        result.references = [Reference(**ref) for ref in payload["references"]]
        result._paths = {ref.image_path for ref in result.references}
        if len(result._paths) != len(result.references):
            raise ValueError("Duplicate reference image paths in mapping")
        if index.ntotal != len(result.references) or not result.references:
            raise ValueError("Index and reference mapping counts do not match or are empty")
        return result
