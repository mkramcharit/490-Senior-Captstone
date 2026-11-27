from dataclasses import asdict, dataclass
import json
from pathlib import Path

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

    def add(self, vectors, references: list[Reference]):
        vectors = normalize(vectors, self.index.d)
        if len(vectors) != len (references):
            raise ValueError("Every embedding must have one reference")
        if not all(isinstance(ref, Reference) for ref in references):
            raise ValueError("References must be Reference objects")
        paths = [ref.image_path for ref in self.references + references]
        if len(set(paths)) != len(paths):
            raise ValueError("Duplicate reference image paths")
        self.index.add(vectors)
        self.references.extend(references)

    def predict(self, vector, top_k: int = 5) -> dict:
        if type(top_k) is not int or top_k < 1:
            raise ValueError("Must be a positive integer")
        if not self.references:
            raise ValueError("Reference index is empty")
        query = normalize(np.asarray(vector).reshape(1, -1), self.index.d)
        scores, positions = self.index.search(query, min(top_k, self.index.ntotal))
        matches = [
            {"landmark_id": self.references[int(pos)].landmark_id,
             "score": float(np.clip(score, -1, 1)),
             "image_path": self.references[int(pos)].image_path}
             for score, pos in zip(scores[0], positions[0])
        ]
        groups = {}
        for match in matches:
            groups.setdefault(match["landmark_id"], []).append(match["score"])
        winner = max(groups, key=lambda key: (
            sum(max(0, s) for s in groups[key]), max(groups[key])
        ))
        similarity = max(groups[winner])
        agreement = len(groups[winner]) / len(matches)
        confidence = max(0.0, similarity) * agreement
        return {"landmark_id": winner, "confidence": confidence,
                "similarity": similarity, "agreement": agreement,
                "top_matches": matches}

    def save(self, directory: str | Path):
        """Create a new artifact directory, don't overwrite an existing index"""
        if not self.references:
            raise ValueError("Cannot save an empty index")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        faiss.write_index(self.index, str(directory / "images.faiss"))
        payload = {"version": 1, "signature": self.signature,
                   "references": [asdict(ref) for ref in self.references]}
        (directory / "references.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, directory: str | Path, expected_signature: str):
        """Load only FAISS artifacts"""
        directory = Path(directory)
        payload = json.loads((directory / "references.json").read_text(encoding="utf-8"))
        if payload["version"] != 1 or payload["signature"] != expected_signature:
            raise ValueError("Index model does not match preprocessing")
        index = faiss.read_index(str(directory / "images.faiss"))
        if not isinstance(index, faiss.IndexFlatIP):
            raise ValueError("Expected a flat inner product index")
        result = cls(index.d, expected_signature)
        result.index = index
        result.references = [Reference(**ref) for ref in payload["references"]]
        if index.ntotal != len(result.references) or not result.references:
            raise ValueError("Index and reference mapping counts do not match or are empty")
        return result
    