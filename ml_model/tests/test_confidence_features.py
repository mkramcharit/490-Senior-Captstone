import numpy as np
import pytest

from landmark_ml.calibration import probability
from landmark_ml.confidence_features import features,fit_features


def test_feature_calibration_learns_signal_on_independent_samples():
    rng=np.random.default_rng(4)
    values=rng.normal(size=(1000,6))
    expected=1/(1+np.exp(-(2*values[:,0]-1.5*values[:,1]+values[:,3])))
    outcomes=rng.random(len(values))<expected
    model=fit_features(values[:600],outcomes[:600])
    predicted=np.array([probability(model,row) for row in values[600:]])
    constant=outcomes[:600].mean()
    assert np.mean((predicted-outcomes[600:])**2) < np.mean((constant-outcomes[600:])**2)-.04


def test_retrieval_features_include_competitor_separation():
    prediction={'landmark_id':1,'similarity':.9,'agreement':.5,
                'top_matches':[{'landmark_id':1,'score':.9},{'landmark_id':2,'score':.8}]}
    values=features(prediction)
    assert values == pytest.approx([.9,.5,.9,.1,.1,0.])


def test_feature_calibration_rejects_missing_outcome_variation():
    with pytest.raises(ValueError):
        fit_features(np.ones((30,6)),np.ones(30))
