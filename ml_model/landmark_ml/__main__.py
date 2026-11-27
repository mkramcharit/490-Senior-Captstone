import argparse
import json
from pathlib import Path

from . import LandmarkPipeline, Reference
from .config import resolve_index, resolve_model

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Embed images from a JSON manifest")
    build.add_argument("manifest", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--batch-size", type=int, default=16)
    predict = commands.add_parser("predict", help="Predict a local image")
    predict.add_argument("index", type=Path)
    predict.add_argument("image", type=Path)
    predict.add_argument("--top-k", type=int, default=5)
    check = commands.add_parser('check', help='Validate installed model and index and print their identity')
    check.add_argument('--index', type=Path)
    package = commands.add_parser('package', help='Export and verify a portable runtime index ZIP')
    package.add_argument('output', type=Path)
    package.add_argument('--index', type=Path)
    for command in (build, predict, check, package):
        command.add_argument("--model")
        command.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.command=="build":
        if args.output.exists():
            parser.error("Output already exists; choose a new index directory")
        rows = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            parser.error("Manifest must be a JSON array")
        references = [Reference(row["landmark_id"], str(args.manifest.parent/row["image_path"])) for row in rows]
        pipeline = LandmarkPipeline.build(references, resolve_model(args.model), args.batch_size, args.device)
        pipeline.save(args.output)
        print(f"Indexed {len(references)} reference images in {args.output}")
    else:
        pipeline = LandmarkPipeline.load(resolve_index(args.index), resolve_model(args.model), args.device)
        if args.command == 'predict':
            result = pipeline.predict(args.image, args.top_k)
        elif args.command == 'check':
            from .artifacts import inspect_pipeline
            result = inspect_pipeline(pipeline)
        else:
            from .artifacts import package_bundle
            result = package_bundle(args.index or pipeline.index_directory, args.output, pipeline)
        print(json.dumps(result, indent=2))
if __name__ == "__main__":
    main()
