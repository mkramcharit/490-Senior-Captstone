from functools import lru_cache
import os
from pathlib import Path

from .pipeline import LandmarkPipeline


@lru_cache(maxsize=4)
def _pipeline(directory, model_path, device):
    return LandmarkPipeline.load(directory, model_path, device)


def recognize_image(image, index_path=None, model_path=None, device='cpu', top_k=5):
    root = Path(__file__).resolve().parents[2]
    directory = Path(index_path or os.getenv('LANDMARK_INDEX_PATH', 'artifacts/landmarks'))
    model = Path(model_path or os.getenv('LANDMARK_MODEL_PATH', 'dinov2-small'))
    if not directory.is_absolute():
        directory = root / directory
    if not model.is_absolute():
        model = root / model
    result = _pipeline(str(directory.resolve()), str(model.resolve()), device).predict(image, top_k)
    probability = result['confidence_probability']
    landmark_id = result['landmark_id']
    return int(landmark_id) if landmark_id is not None else None, float(probability) if probability is not None else None
