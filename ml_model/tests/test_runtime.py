import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import numpy as np
import pytest

from landmark_ml import LandmarkPipeline, Reference, ReferenceIndex
from landmark_ml.artifacts import package_bundle, verify_bundle
from landmark_ml.config import resolve_index
from landmark_ml.decision import RecognitionPolicy


def sample(tmp_path, monkeypatch):
    index = ReferenceIndex(2, 'model')
    index.add([[1, 0], [.99, .1], [0, 1]], [Reference(7, 'neon:a'), Reference(7, 'neon:b'), Reference(8, 'neon:c')])
    embedder = SimpleNamespace(signature='model', dimension=2, model_path=tmp_path / 'model', embed=lambda images: np.array([[1, 0]]))
    monkeypatch.setattr('landmark_ml.pipeline.DinoV2Embedder', lambda *args: embedder)
    pipeline = LandmarkPipeline(embedder, index, RecognitionPolicy(minimum_similarity=.85))
    directory = tmp_path / 'bundle'
    pipeline.save(directory)
    return LandmarkPipeline.load(directory), directory


def test_batched_queries_preserve_single_query_results():
    index = ReferenceIndex(2, 'model')
    index.add([[1, 0], [0, 1]], [Reference(7, 'a'), Reference(8, 'b')])
    vectors = np.array([[1, .1], [.1, 1]])
    assert index.predict_batch(vectors) == [index.predict(vector) for vector in vectors]


def test_saved_policy_and_calibration_survive_round_trip(tmp_path, monkeypatch):
    pipeline, directory = sample(tmp_path, monkeypatch)
    assert pipeline.recognition_policy.minimum_similarity == .85
    assert pipeline.predict(b'image')['landmark_id'] == 7
    from landmark_ml.calibration import index_signature
    from dataclasses import asdict
    pipeline.calibrator = {'version': 1, 'method': 'regularized_sigmoid', 'top_k': 5,
                           'mean': .5, 'scale': .2, 'weights': [0, 1], 'score_range': [0, 1],
                           'index_signature': index_signature(pipeline.index),
                           'recognition_policy': asdict(pipeline.recognition_policy)}
    pipeline.save(tmp_path / 'second')
    restored = LandmarkPipeline.load(tmp_path / 'second')
    assert restored.calibrator == pipeline.calibrator
    assert restored.predict(b'image')['confidence_calibrated']


def test_export_round_trip_checksums_and_rejects_modified_files(tmp_path, monkeypatch):
    pipeline, directory = sample(tmp_path, monkeypatch)
    output = tmp_path / 'runtime.zip'
    result = package_bundle(directory, output, pipeline)
    assert result['reference_count'] == 3
    installed = tmp_path / 'installed'
    with zipfile.ZipFile(output) as archive:
        archive.extractall(installed)
    assert verify_bundle(installed)['checksums_verified']
    loaded = LandmarkPipeline.load(installed)
    assert loaded.predict(b'image')['landmark_id'] == 7
    (installed / 'references.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum mismatch'):
        LandmarkPipeline.load(installed)


def test_manifest_rejects_unlisted_runtime_configuration(tmp_path, monkeypatch):
    pipeline, directory = sample(tmp_path, monkeypatch)
    output = tmp_path / 'runtime.zip'
    package_bundle(directory, output, pipeline)
    installed = tmp_path / 'installed'
    with zipfile.ZipFile(output) as archive:
        archive.extractall(installed)
    (installed / 'calibration.json').write_text('{}')
    with pytest.raises(ValueError, match='Unverified'):
        verify_bundle(installed)


def test_mapping_rejects_duplicate_image_ids(tmp_path):
    index = ReferenceIndex(2, 'model')
    index.add([[1, 0], [0, 1]], [Reference(7, 'a'), Reference(8, 'b')])
    index.save(tmp_path / 'index')
    path = tmp_path / 'index/references.json'
    mapping = json.loads(path.read_text())
    mapping['references'][1]['image_path'] = 'a'
    path.write_text(json.dumps(mapping))
    with pytest.raises(ValueError, match='Duplicate'):
        ReferenceIndex.load(path.parent, 'model')


def test_default_prefers_full_index_and_explicit_setting_does_not_fall_back(tmp_path, monkeypatch):
    monkeypatch.delenv('LANDMARK_INDEX_PATH', raising=False)
    monkeypatch.setattr('landmark_ml.config.project_root', lambda: tmp_path)
    full = tmp_path / 'artifacts/ML/indexes/full-neon/handoff'
    legacy = tmp_path / 'artifacts/landmarks'
    for directory in (full, legacy):
        directory.mkdir(parents=True)
        for name in ('images.faiss', 'references.json'):
            (directory / name).touch()
    assert resolve_index() == full.resolve()
    monkeypatch.setenv('LANDMARK_INDEX_PATH', 'missing')
    assert resolve_index() == (tmp_path / 'missing').resolve()


def test_interrupted_save_does_not_publish_partial_index(tmp_path, monkeypatch):
    index = ReferenceIndex(2, 'model')
    index.add([[1, 0]], [Reference(7, 'a')])
    def fail(*args):
        raise OSError('disk write interrupted')
    monkeypatch.setattr('landmark_ml.retrieval.faiss.write_index', fail)
    with pytest.raises(OSError):
        index.save(tmp_path / 'index')
    assert not list(tmp_path.iterdir())


def test_unapproved_calibration_cannot_be_loaded(tmp_path):
    from landmark_ml.calibration import load
    path = tmp_path / 'calibration.json'
    path.write_text(json.dumps({'version': 1, 'method': 'regularized_sigmoid', 'deployment_status': 'not_approved'}))
    with pytest.raises(ValueError, match='not approved'):
        load(path, None)


def test_default_does_not_silently_load_legacy_demo(tmp_path, monkeypatch):
    monkeypatch.delenv('LANDMARK_INDEX_PATH', raising=False)
    monkeypatch.setattr('landmark_ml.config.project_root', lambda: tmp_path)
    legacy = tmp_path / 'artifacts/landmarks'
    legacy.mkdir(parents=True)
    for name in ('images.faiss', 'references.json'):
        (legacy / name).touch()
    with pytest.raises(FileNotFoundError, match='No reference index'):
        resolve_index()
