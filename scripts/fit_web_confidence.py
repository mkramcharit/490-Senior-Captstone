import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ml_model'))
from landmark_ml import LandmarkPipeline
from landmark_ml.calibration import fit, index_signature, probability
from landmark_ml.confidence_features import features, fit_features


def save(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    temporary.replace(path)


def select_model(rows, seed=20261029):
    groups = sorted({row['group_id'] for row in rows})
    rng = np.random.default_rng(seed)
    rng.shuffle(groups)
    folds = {group:i%5 for i,group in enumerate(groups)}
    losses = {'score_only':[], 'features':[]}
    for fold in range(5):
        train = [row for row in rows if folds[row['group_id']]!=fold]
        test = [row for row in rows if folds[row['group_id']]==fold]
        score_model = fit([row['match_score'] for row in train],[row['correct'] for row in train])
        feature_model = fit_features([row['features'] for row in train],[row['correct'] for row in train])
        for row in test:
            losses['score_only'].append((probability(score_model,row['match_score'])-row['correct'])**2)
            losses['features'].append((probability(feature_model,row['features'])-row['correct'])**2)
    means = {name:float(np.mean(values)) for name,values in losses.items()}
    selected = 'features' if means['features'] < means['score_only']-.002 else 'score_only'
    return selected, means


def main():
    import faiss
    import torch
    parser = argparse.ArgumentParser()
    parser.add_argument('index',type=Path)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--model',default='dinov2-small')
    parser.add_argument('--device',default='cpu')
    args=parser.parse_args()
    torch.set_num_threads(4)
    faiss.omp_set_num_threads(4)
    pipeline=LandmarkPipeline.load(args.index,args.model,args.device)
    pipeline.calibrator=None
    pipeline.embedder.preprocess_workers=4
    source=json.loads(args.manifest.read_text(encoding='utf-8'))
    if not source or any(row.get('ground_truth_verified') is not True for row in source):
        parser.error('Use verified development labels')
    args.output.mkdir(parents=True,exist_ok=True)
    path=args.output/'retrieval-development.json'
    results=json.loads(path.read_text()) if path.exists() else []
    completed={row['sha256'] for row in results}
    pending=[row for row in source if row['sha256'] not in completed]
    for start in range(0,len(pending),16):
        batch=pending[start:start+16]
        paths=[args.manifest.parent/row['image_path'] for row in batch]
        for row,image in zip(batch,paths):
            if hashlib.sha256(image.read_bytes()).hexdigest()!=row['sha256']:
                raise ValueError('Development photo changed after annotation')
        vectors=pipeline.embedder.embed(paths)
        for row,prediction in zip(batch,pipeline.index.predict_batch(vectors,5)):
            accepted=pipeline.recognition_policy.evaluate(prediction)['accepted']
            results.append({**row,'used_for_development':True,'split':'calibration',
                            'correct':prediction['landmark_id'] in row['landmark_ids'],'accepted':accepted,
                            'match_score':prediction['match_score'],'features':features(prediction)})
        save(path,results)
        print(json.dumps({'development_evaluated':len(results),'total':len(source)}),flush=True)
    accepted=[row for row in results if row['accepted']]
    selected,losses=select_model(accepted)
    if selected=='features':
        model=fit_features([row['features'] for row in accepted],[row['correct'] for row in accepted])
    else:
        model=fit([row['match_score'] for row in accepted],[row['correct'] for row in accepted])
    model.update(index_signature=index_signature(pipeline.index),top_k=5,recognition_policy=asdict(pipeline.recognition_policy),
                 deployment_status='not_approved',population='accepted_predictions',dataset='source_verified_web_photos',
                 score_range=[min(row['match_score'] for row in accepted),max(row['match_score'] for row in accepted)],
                 calibration_image_hashes=[row['sha256'] for row in accepted])
    save(args.output/'calibration-candidate.json',model)
    save(args.output/'selection.json',{'method':selected,'grouped_cross_validation_brier':losses,
                                     'calibration_samples':len(accepted),'calibration_errors':sum(not row['correct'] for row in accepted),
                                     'group_count':len({row['group_id'] for row in accepted}),'independent_confirmation_pending':True})
    print(json.dumps({'selected':selected,'cross_validation_brier':losses}),flush=True)


if __name__=='__main__':
    main()
