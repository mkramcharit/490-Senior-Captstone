import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from landmark_ml import LandmarkPipeline, Reference, ReferenceIndex

spec = importlib.util.spec_from_file_location('calibrate_full_index', Path(__file__).resolve().parents[2] / 'scripts/calibrate_full_index.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_evaluation_keeps_rejections_in_denominator_and_limits_displayed_probabilities():
    rows = [{'match_score': .9, 'correct': True, 'accepted': True, 'known_to_index': True},
            {'match_score': .7, 'correct': False, 'accepted': True, 'known_to_index': False},
            {'match_score': .1, 'correct': False, 'accepted': False, 'known_to_index': False}]
    model = {'mean': .5, 'scale': 1, 'weights': [0, 2], 'sample_count': 30, 'correct_count': 10, 'score_range': [.2, .8]}
    report = module.summarize(rows, model)
    assert report['all_candidates']['sample_count'] == 3
    assert report['accepted_count'] == 2
    assert report['unsupported_false_acceptance_rate'] == .5
    assert report['displayed_probability_count'] == 1
    assert report['displayed_probability_metrics']['sample_count'] == 1


def test_changed_recognition_policy_disables_fitted_probability():
    index = ReferenceIndex(2, 'test')
    index.add([[1, 0]], [Reference(1, 'neon:1')])
    embedder = SimpleNamespace(signature='test', dimension=2, embed=lambda photos: np.array([[1, 0]]))
    pipeline = LandmarkPipeline(embedder, index)
    pipeline.calibrator = {'top_k': 5, 'mean': 0, 'scale': 1, 'weights': [0, 0], 'recognition_policy': {'minimum_similarity': .3}}
    result = pipeline.predict(b'image')
    assert result['confidence'] is None
    assert not result['confidence_calibrated']
    assert 'rules differ' in result['confidence_description']

def test_collection_balances_known_and_unknown_without_reference_id_overlap(tmp_path, monkeypatch):
    import csv
    import io
    import tarfile
    from PIL import Image
    root = tmp_path / 'experiment'
    root.mkdir()
    labels = []
    archive_path = root / 'source.tar'
    rng = np.random.default_rng(27)
    with tarfile.open(archive_path, 'w') as archive:
        for i in range(12):
            key = f'{i:016x}'
            split = 'Public' if i < 6 else 'Private'
            label = '1' if i % 6 < 3 else ''
            labels.append({'id': key, 'landmarks': label, 'Usage': split})
            output = io.BytesIO()
            Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(output, format='JPEG')
            body = output.getvalue()
            member = tarfile.TarInfo(key + '.jpg')
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
    with (root / 'recognition_solution_v2.1.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'landmarks', 'Usage'])
        writer.writeheader()
        writer.writerows(labels)
    pipeline = SimpleNamespace(index=SimpleNamespace(references=[Reference(1, 'neon:0000000000000000')], _paths={'neon:0000000000000000'}))
    monkeypatch.setattr(module, 'cache_archive', lambda *args, **kwargs: archive_path)
    monkeypatch.setattr(module, 'require_space', lambda *args: None)
    rows = module.collect(root, pipeline, 4)
    assert len(rows) == 8
    assert not any(r['id'] == '0000000000000000' for r in rows)
    for split in ['calibration', 'test']:
        for covered in [True, False]:
            assert sum(r['split'] == split and r['known_to_index'] == covered for r in rows) == 2
    assert not {r['id'] for r in rows if r['split'] == 'calibration'} & {r['id'] for r in rows if r['split'] == 'test'}
