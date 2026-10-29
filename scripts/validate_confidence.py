import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ml_model'))
from landmark_ml import LandmarkPipeline
from landmark_ml.calibration import index_signature, probability
from landmark_ml.validation import review_predictions


def save(path, content):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(content, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    import faiss
    import torch
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('protocol', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--model', default='dinov2-small')
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    model = json.loads(args.candidate.read_text(encoding='utf-8'))
    protocol = json.loads(args.protocol.read_text(encoding='utf-8'))
    if hashlib.sha256(args.candidate.read_bytes()).hexdigest() != protocol['candidate_sha256']:
        parser.error('The frozen calibrator changed after validation was planned')
    rows = json.loads(args.manifest.read_text(encoding='utf-8'))
    score_range = protocol.get('evaluation_score_range', model['score_range'])
    if not rows or any(row.get('ground_truth_verified') is not True or row.get('split') != 'test' for row in rows):
        parser.error('Use independently verified test images only')
    if len({row['sha256'] for row in rows}) != len(rows):
        parser.error('Duplicate validation photos')
    torch.set_num_threads(4)
    faiss.omp_set_num_threads(4)
    pipeline = LandmarkPipeline.load(args.index, args.model, args.device)
    pipeline.embedder.preprocess_workers = 4
    pipeline.calibrator = None
    if model['index_signature'] != index_signature(pipeline.index) or model['recognition_policy'] != asdict(pipeline.recognition_policy):
        parser.error('Calibrator index or recognition policy mismatch')
    args.output.mkdir(parents=True, exist_ok=True)
    configuration = {'candidate_sha256': protocol['candidate_sha256'],
                     'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                     'protocol_sha256': hashlib.sha256(args.protocol.read_bytes()).hexdigest()}
    config_path = args.output / 'configuration.json'
    if config_path.exists() and json.loads(config_path.read_text()) != configuration:
        parser.error('Validation inputs changed; use a fresh output directory')
    save(config_path, configuration)
    output = args.output / 'predictions.json'
    results = json.loads(output.read_text()) if output.exists() else []
    completed = {row['sha256'] for row in results}
    pending = [row for row in rows if row['sha256'] not in completed]
    for start in range(0, len(pending), 16):
        batch = pending[start:start+16]
        paths = [args.manifest.parent / row['image_path'] for row in batch]
        for row, path in zip(batch, paths):
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Validation image changed after annotation')
        vectors = pipeline.embedder.embed(paths)
        for row, prediction in zip(batch, pipeline.index.predict_batch(vectors, model['top_k'])):
            accepted = pipeline.recognition_policy.evaluate(prediction)['accepted']
            eligible = accepted and score_range[0] <= prediction['match_score'] <= score_range[1]
            value = probability(model, prediction) if eligible else None
            if value is not None and value < protocol['minimum_probability']:
                value = None
            results.append({**row, 'candidate_landmark_id': prediction['landmark_id'],
                            'correct': prediction['landmark_id'] in row['landmark_ids'],
                            'accepted': accepted, 'match_score': prediction['match_score'], 'probability': value})
        save(output, results)
        print(json.dumps({'evaluated':len(results), 'total':len(rows)}), flush=True)
    report = {**configuration, **review_predictions(results, protocol), 'installed_in_runtime':False}
    save(args.output / 'evaluation.json', report)
    if report['eligible']:
        approved = {**model, 'version':2, 'deployment_status':'approved', 'original_fitted_score_range':model['score_range'],
                    'score_range':score_range, 'validated_probability_range':[protocol['minimum_probability'],1.],
                    'validation_scope': report['scope'], 'validation_report_sha256':hashlib.sha256((args.output / 'evaluation.json').read_bytes()).hexdigest(),
                    'validation_sample_count': report['displayed_probability_count'],
                    'validation_metrics':report['probability_metrics']}
        save(args.output / 'approved-calibration.json', approved)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
