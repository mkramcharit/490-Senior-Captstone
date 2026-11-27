from functools import lru_cache
from threading import RLock

from .pipeline import LandmarkPipeline
from .config import resolve_index, resolve_model


_load_lock = RLock()


@lru_cache(maxsize=1)
def _pipeline(directory, model_path, device):
    return LandmarkPipeline.load(directory, model_path, device)


def recognize_image(image, index_path=None, model_path=None, device='cpu', top_k=5):
    result = predict_image(image, index_path, model_path, device, top_k)
    probability = result['confidence_probability']
    landmark_id = result['landmark_id']
    return int(landmark_id) if landmark_id is not None else None, float(probability) if probability is not None else None


def predict_image(image, index_path=None, model_path=None, device='cpu', top_k=5):
    directory = resolve_index(index_path)
    model = resolve_model(model_path)
    with _load_lock:
        pipeline = _pipeline(str(directory), str(model), device)
    return pipeline.predict(image, top_k)


def clear_model_cache():
    with _load_lock:
        _pipeline.cache_clear()
