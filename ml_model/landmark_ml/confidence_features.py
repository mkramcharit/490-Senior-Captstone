import numpy as np


FEATURES = ['similarity', 'agreement', 'support_mean', 'competing_gap', 'nearest_gap', 'unanimous']


def features(prediction):
    matches = prediction['top_matches']
    support = [row['score'] for row in matches if row['landmark_id'] == prediction['landmark_id']]
    competitors = [row['score'] for row in matches if row['landmark_id'] != prediction['landmark_id']]
    gap = prediction['similarity'] - max(competitors) if competitors else 0.
    nearest_gap = matches[0]['score'] - matches[1]['score'] if len(matches) > 1 else 0.
    values = [prediction['similarity'], prediction['agreement'], float(np.mean(support)), gap, nearest_gap, float(not competitors)]
    if not support or not np.isfinite(values).all():
        raise ValueError('Invalid retrieval confidence features')
    return values


def fit_features(values, outcomes):
    from .calibration import sigmoid
    values, outcomes = np.asarray(values, dtype=float), np.asarray(outcomes, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(FEATURES) or len(values) < 20 or outcomes.shape != (len(values),):
        raise ValueError('Use at least 20 paired retrieval feature vectors and outcomes')
    if not np.isfinite(values).all() or not np.isin(outcomes, [0,1]).all() or min(sum(outcomes==0),sum(outcomes==1)) < 5:
        raise ValueError('Feature calibration requires finite values and at least five correct and incorrect predictions')
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale[scale < 1e-8] = 1.
    design = np.column_stack([np.ones(len(values)),(values-mean)/scale])
    weights = np.zeros(design.shape[1])
    weights[0] = np.log(outcomes.mean()/(1-outcomes.mean()))
    penalty = np.eye(len(weights))
    penalty[0,0] = 0.
    for _ in range(100):
        probabilities = sigmoid(design@weights)
        gradient = design.T@(probabilities-outcomes)+penalty@weights
        hessian = design.T@((probabilities*(1-probabilities))[:,None]*design)+penalty
        step = np.linalg.solve(hessian+np.eye(len(weights))*1e-8,gradient)
        weights -= step
        if np.linalg.norm(step) < 1e-8:
            break
    return {'version':2,'method':'regularized_logistic_features','features':FEATURES,
            'feature_mean':mean.tolist(),'feature_scale':scale.tolist(),'weights':weights.tolist(),
            'sample_count':len(values),'correct_count':int(outcomes.sum())}


def feature_probability(model, prediction):
    from .calibration import sigmoid
    values = np.asarray(features(prediction) if isinstance(prediction,dict) else prediction,dtype=float)
    if values.shape != (len(FEATURES),) or not np.isfinite(values).all():
        raise ValueError('Confidence feature vector is invalid')
    normalized = (values-np.asarray(model['feature_mean']))/np.asarray(model['feature_scale'])
    return float(sigmoid(model['weights'][0]+normalized@np.asarray(model['weights'][1:])))
