import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import faiss

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ml_model'))
from landmark_ml import LandmarkPipeline
from landmark_ml.calibration import fit, index_signature, metrics, probability


def audit_uploads(manifest, index):
    rows = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(rows, list) or not rows:
        raise ValueError('Provide a nonempty labeled upload manifest')
    seen = {}
    groups = {}
    checked = []
    for row in rows:
        split = row.get('split')
        if split not in ('development', 'calibration', 'test'):
            raise ValueError('Every photo needs a development, calibration, or test split')
        if row.get('ground_truth_verified') is not True or not row.get('expected_name'):
            raise ValueError('Verify the correct landmark name and IDs before evaluation')
        if split == 'test' and row.get('used_for_development'):
            raise ValueError('A photo used to develop recognition rules cannot be a final test example')
        labels = row.get('landmark_ids')
        if not isinstance(labels, list) or any(type(label) is not int for label in labels):
            raise ValueError('Use integer landmark_ids, or an empty list for a landmark not in the catalog')
        path = (manifest.parent / row['image_path']).resolve()
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if digest in seen:
            raise ValueError('Duplicate photo in upload manifest')
        seen[digest] = split
        source_id = row.get('reference_image_id', path.stem)
        if 'neon:' + str(source_id) in index._paths or str(path) in index._paths:
            raise ValueError('Upload photo is already part of the reference index')
        group = row.get('group_id', digest)
        if group in groups and groups[group] != split:
            raise ValueError('Source photo group overlaps calibration, development, or test')
        groups[group] = split
        checked.append({**row, 'path': str(path), 'sha256': digest})
    return checked


def main():
    import torch
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--model', default='dinov2-small')
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory')
    torch.set_num_threads(4)
    faiss.omp_set_num_threads(4)
    pipeline = LandmarkPipeline.load(args.index, args.model, args.device)
    pipeline.calibrator = None
    records = audit_uploads(args.manifest.resolve(), pipeline.index)
    args.output.mkdir(parents=True)
    results = []
    known = {r.landmark_id for r in pipeline.index.references}
    for row in records:
        result = pipeline.predict(row['path'])
        results.append({**row, 'candidate_landmark_id': result['candidate_landmark_id'],
                        'returned_landmark_id': result['landmark_id'], 'accepted': result['landmark_id'] is not None,
                        'correct': result['candidate_landmark_id'] in row['landmark_ids'],
                        'known_to_index': any(label in known for label in row['landmark_ids']),
                        'match_score': result['match_score'], 'prediction_status': result['prediction_status']})
        (args.output / 'predictions.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps({'photo': row['image_path'], 'split': row['split'], 'status': result['prediction_status']}), flush=True)
    calibration = [r for r in results if r['split'] == 'calibration' and r['accepted']]
    test = [r for r in results if r['split'] == 'test']
    accepted_test = [r for r in test if r['accepted']]
    report = {'source': 'user-provided frontend upload photos', 'installed_in_runtime': False,
              'calibration_population': 'accepted predictions only', 'recognition_policy': asdict(pipeline.recognition_policy),
              'development_count': sum(r['split'] == 'development' for r in results),
              'calibration_accepted_count': len(calibration), 'test_count': len(test), 'test_accepted_count': len(accepted_test),
              'test_rejection_count': len(test) - len(accepted_test),
              'limitations': ['Label correctness depends on the supplied verified ground truth.',
                              'Reference-ID overlap and query duplicates are checked; all training photo content was not available for an exhaustive visual-duplicate audit.',
                              'Fit requirements are minimum sanity checks, not proof that the sample is large or representative enough.']}
    try:
        if len(test) < 20 or not accepted_test:
            raise ValueError('Need a separate test set of at least 20 photos, with accepted predictions to evaluate')
        model = fit([r['match_score'] for r in calibration], [r['correct'] for r in calibration])
        model.update(index_signature=index_signature(pipeline.index), top_k=5, recognition_policy=asdict(pipeline.recognition_policy),
                     population='accepted_predictions', deployment_status='not_approved', dataset='verified_frontend_uploads', calibration_image_hashes=[r['sha256'] for r in calibration])
        eligible = [r for r in accepted_test if model['score_range'][0] <= r['match_score'] <= model['score_range'][1]]
        if not eligible:
            raise ValueError('No accepted test scores fall within the calibration range')
        report.update(status='candidate_evaluated_not_deployed', confidence_test_count=len(eligible),
                      accepted_test_accuracy=sum(r['correct'] for r in accepted_test) / len(accepted_test),
                      probability_metrics=metrics([probability(model, r['match_score']) for r in eligible], [r['correct'] for r in eligible]))
        (args.output / 'calibration-candidate.json').write_text(json.dumps(model, indent=2), encoding='utf-8')
    except ValueError as error:
        report.update(status='insufficient_data_for_calibration', reason=str(error))
    (args.output / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
