from pathlib import Path
from .embeddings import DinoV2Embedder, ImageInput
from .retrieval import Reference, ReferenceIndex

class LandmarkPipeline:
    def __init__(self, embedder: DinoV2Embedder, index: ReferenceIndex):
        if index.signature != embedder.signature or index.index.d != embedder.dimension:
            raise ValueError("Embedder and reference index are incompatible")
        self.embedder = embedder
        self.index = index
        self.calibrator = None

    @classmethod
    def build(cls, references: list[Reference], model_path="dinov2-small", batch_size=16, device="cpu"):
        if not references:
            raise ValueError("Provide reference images before building the index")
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        references = [Reference(ref.landmark_id, str(Path(ref.image_path).resolve())) for ref in references]
        paths = [ref.image_path for ref in references]
        if len(set(paths)) != len(paths):
            raise ValueError("Duplicate reference image paths")
        for path in paths:
            if not Path(path).is_file():
                raise FileNotFoundError(path)
        embedder = DinoV2Embedder(model_path, device)
        index = ReferenceIndex(embedder.dimension, embedder.signature)
        for start in range(0, len(references), batch_size):
            batch = references[start:start + batch_size]
            index.add(embedder.embed([ref.image_path for ref in batch]), batch)
        return cls(embedder, index)

    @classmethod
    def load(cls, directory, model_path="dinov2-small", device="cpu"):
        embedder = DinoV2Embedder(model_path, device)
        pipeline = cls(embedder, ReferenceIndex.load(directory, embedder.signature))
        calibration_path = Path(directory) / "calibration.json"
        if calibration_path.is_file():
            from .calibration import load
            pipeline.calibrator = load(calibration_path, pipeline.index)
        return pipeline

    def predict(self, image: ImageInput, top_k: int = 5) -> dict:
        result = self.index.predict(self.embedder.embed([image])[0], top_k)
        if self.calibrator is not None and top_k == self.calibrator["top_k"]:
            from .calibration import probability
            result["confidence_probability"] = probability(self.calibrator, result["match_score"])
            result["confidence_calibrated"] = True
        return result

    def save(self, directory):
        self.index.save(directory)
