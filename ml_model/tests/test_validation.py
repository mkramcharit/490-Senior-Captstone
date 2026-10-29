from types import SimpleNamespace

import numpy as np
import pytest

from landmark_ml import LandmarkPipeline, Reference, ReferenceIndex
from landmark_ml.validation import review_predictions, wilson_interval


def protocol():
    return {'bootstrap_seed': 1, 'minimum_displayed_predictions': 100, 'minimum_source_groups': 30,
            'minimum_represented_known_sites': 5, 'maximum_ece': .05,
            'maximum_absolute_calibration_bias_interval_95': .1,
            'paired_brier_vs_raw_upper_95_maximum': 0, 'maximum_unsupported_false_acceptance_upper_95': .05}


def sample():
    rows = [{'site':f'site{i%5}', 'group_id':f'group{i}', 'landmark_ids':[i%5], 'correct':i%20!=0,
             'accepted':True, 'probability':.95, 'match_score':.6} for i in range(200)]
    rows.extend({'site':'unknown', 'group_id':f'unknown{i}', 'landmark_ids':[], 'correct':False,
                 'accepted':False, 'probability':None, 'match_score':.1} for i in range(200))
    return rows


def test_representative_correctness_passes_predeclared_checks():
    report = review_predictions(sample(), protocol())
    assert report['eligible']
    assert report['displayed_probability_count'] == 200
    assert report['unsupported_queries'] == 200


def test_overconfident_model_and_unknown_guesses_fail():
    rows = sample()
    for row in rows[:100]:
        row['correct'] = False
    for row in rows[200:230]:
        row['accepted'] = True
    report = review_predictions(rows, protocol())
    assert not report['eligible']
    assert 'calibration_error' in report['failed_checks']
    assert 'unsupported_false_acceptance' in report['failed_checks']


def test_repeated_photographer_does_not_supply_independent_groups():
    rows = sample()
    for row in rows:
        row['group_id'] = 'same-series'
    assert 'source_group_count' in review_predictions(rows, protocol())['failed_checks']


def test_pipeline_withholds_unvalidated_probability_range():
    index = ReferenceIndex(2, 'test')
    index.add([[1, 0]], [Reference(1, 'neon:1')])
    embedder = SimpleNamespace(signature='test', dimension=2, embed=lambda images:np.array([[1,0]]))
    pipeline = LandmarkPipeline(embedder,index)
    pipeline.calibrator = {'top_k':5,'mean':0,'scale':1,'weights':[0,0], 'validated_probability_range':[.8,1.]}
    result = pipeline.predict(b'image')
    assert result['confidence'] is None
    assert not result['confidence_calibrated']
    assert 'validated range' in result['confidence_description']


def test_wilson_interval_accounts_for_uncertainty():
    assert wilson_interval(0,10)[1] > wilson_interval(0,100)[1]
    with pytest.raises(ValueError):
        wilson_interval(0,0)


def test_validated_format_requires_evidence_and_preserves_parameters(tmp_path):
    import json
    from landmark_ml.calibration import index_signature, load
    index = ReferenceIndex(2, 'test')
    index.add([[1,0]],[Reference(1,'a')])
    model = {'version':2, 'method':'regularized_sigmoid', 'deployment_status':'approved',
             'validation_scope':'Independent selected web photos', 'validation_sample_count':100,
             'validated_probability_range':[.8,1.], 'validation_report_sha256':'a'*64,
             'index_signature':index_signature(index), 'mean':0., 'scale':1., 'weights':[0.,1.], 'top_k':5}
    path = tmp_path / 'calibration.json'
    path.write_text(json.dumps(model))
    assert load(path,index) == model
    model['validation_sample_count'] = 12
    path.write_text(json.dumps(model))
    with pytest.raises(ValueError,match='insufficient'):
        load(path,index)


def test_installer_refuses_failed_validation_before_touching_index(tmp_path,monkeypatch):
    import importlib.util
    import json
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('install_calibration', Path(__file__).resolve().parents[2] / 'scripts/install_calibration.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    report = tmp_path / 'evaluation.json'
    report.write_text(json.dumps({'eligible':False,'failed_checks':['calibration_error']}))
    monkeypatch.setattr('sys.argv',['install_calibration',str(tmp_path/'index'),str(tmp_path/'candidate.json'),str(report)])
    with pytest.raises(SystemExit):
        installer.main()
    assert not (tmp_path/'index').exists()
