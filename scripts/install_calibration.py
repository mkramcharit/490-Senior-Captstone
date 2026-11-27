import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ml_model'))
from landmark_ml import LandmarkPipeline
from landmark_ml.calibration import load


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('calibration', type=Path)
    parser.add_argument('evaluation', type=Path)
    parser.add_argument('--model', default='dinov2-small')
    args = parser.parse_args()
    report = json.loads(args.evaluation.read_text(encoding='utf-8'))
    if report.get('eligible') is not True or report.get('failed_checks'):
        parser.error('Independent validation did not pass; calibration will not be installed')
    pipeline = LandmarkPipeline.load(args.index, args.model)
    model = load(args.calibration, pipeline.index)
    digest = hashlib.sha256(args.evaluation.read_bytes()).hexdigest()
    if model.get('version') != 2 or model.get('validation_report_sha256') != digest:
        parser.error('Approved model does not match this independent validation report')
    target = args.index / 'calibration.json'
    if target.exists():
        backup = args.index / ('calibration-backup-' + hashlib.sha256(target.read_bytes()).hexdigest()[:12] + '.json')
        if not backup.exists():
            backup.write_bytes(target.read_bytes())
    body = args.calibration.read_bytes()
    temporary = target.with_suffix('.pending')
    temporary.write_bytes(body)
    temporary.replace(target)
    manifest_path = args.index / 'ml-version.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['files']['calibration.json'] = hashlib.sha256(body).hexdigest()
        temporary = manifest_path.with_suffix('.pending')
        temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        temporary.replace(manifest_path)
    installed = load(target, pipeline.index)
    assert installed['validation_report_sha256'] == digest
    print(json.dumps({'installed':str(target.resolve()), 'validation_sample_count':installed['validation_sample_count'],
                      'validated_probability_range':installed['validated_probability_range'], 'validation_scope':installed['validation_scope']}))


if __name__ == '__main__':
    main()
