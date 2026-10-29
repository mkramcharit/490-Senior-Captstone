from pathlib import Path
from dataclasses import asdict
import json
from threading import RLock
from .embeddings import DinoV2Embedder, ImageInput
from .retrieval import Reference, ReferenceIndex
from .decision import RecognitionPolicy

class LandmarkPipeline:
    def __init__(self, embedder: DinoV2Embedder, index: ReferenceIndex, recognition_policy=None):
        if index.signature != embedder.signature or index.index.d != embedder.dimension:
            raise ValueError("Embedder and reference index are incompatible")
        self.embedder = embedder
        self.index = index
        self.calibrator = None
        self.recognition_policy = recognition_policy or RecognitionPolicy()
        self.index_directory = None
        self.indexed_landmark_count = len({ref.landmark_id for ref in index.references})
        self._prediction_lock = RLock()

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
        from .artifacts import verify_bundle
        verify_bundle(directory)
        embedder = DinoV2Embedder(model_path, device)
        policy_path = Path(directory) / 'recognition-policy.json'
        policy = RecognitionPolicy(**json.loads(policy_path.read_text(encoding='utf-8'))) if policy_path.is_file() else None
        pipeline = cls(embedder, ReferenceIndex.load(directory, embedder.signature), policy)
        pipeline.index_directory = str(Path(directory).resolve())
        calibration_path = Path(directory) / "calibration.json"
        if calibration_path.is_file():
            from .calibration import load
            pipeline.calibrator = load(calibration_path, pipeline.index)
        return pipeline

    def predict(self, image: ImageInput, top_k: int = 5) -> dict:
        with self._prediction_lock:
            result = self.index.predict(self.embedder.embed([image])[0], top_k)
        reason = 'No compatible calibrator installed for this index.'
        compatible = self.calibrator is not None and top_k == self.calibrator['top_k']
        if self.calibrator is not None and not compatible:
            reason = 'Search configuration differs from the fitted calibrator.'
        if compatible and self.calibrator.get('recognition_policy', asdict(self.recognition_policy)) != asdict(self.recognition_policy):
            compatible = False
            reason = 'Recognition rules differ from the fitted calibrator.'
        if compatible and 'score_range' in self.calibrator:
            lower, upper = self.calibrator['score_range']
            if not lower <= result['match_score'] <= upper:
                compatible = False
                reason = 'Match score is outside the fitted calibration range.'
        if compatible:
            from .calibration import probability
            value = probability(self.calibrator, result)
            lower, upper = self.calibrator.get('validated_probability_range', [0., 1.])
            if lower <= value <= upper:
                result["confidence_probability"] = value
                result["confidence_calibrated"] = True
            else:
                reason = 'Estimated probability is outside the independently validated range.'
        result['confidence'] = result['confidence_probability']
        result['confidence_description'] = ('Estimated correctness probability for data comparable to the calibration set.'
                                            if result['confidence_calibrated'] else reason)
        decision = self.recognition_policy.evaluate(result)
        result['candidate_landmark_id'] = result['landmark_id']
        result['recognition_decision'] = decision
        result['prediction_status'] = 'candidate' if decision['accepted'] else 'unknown'
        if not decision['accepted']:
            result['landmark_id'] = None
            result['confidence'] = None
            result['confidence_probability'] = None
            result['confidence_calibrated'] = False
            result['confidence_description'] = 'Unable to identify this landmark reliably from the reference collection.'
        result['index_info'] = {'directory': self.index_directory, 'reference_count': self.index.index.ntotal,
                                'landmark_count': self.indexed_landmark_count, 'dimension': self.index.index.d}
        result['match_score_description'] = 'Similarity and reference agreement; not a probability of correctness.'
        result['confidence_validation_scope'] = self.calibrator.get('validation_scope') if self.calibrator else None
        return result

    def save(self, directory):
        extra_files = {'recognition-policy.json': asdict(self.recognition_policy)}
        if self.calibrator is not None:
            extra_files['calibration.json'] = self.calibrator
        self.index.save(directory, extra_files=extra_files)
