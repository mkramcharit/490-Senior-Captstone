import argparse
import json
from pathlib import Path

from . import LandmarkPipeline, Reference

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Embed images from a JSON manifest")
    build.add_argument("manifest", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--batch--size", type=int, default=16)
    predict = commands.add_parser("predict", help="Predict a local image")
    predict.add_argument("index", type=Path)
    predict.add_argument("image", type=Path)
    predict.add_argument("--top-k", type=int, default=5)
    for command in (build, predict):
        command.add_argument("--model", default="dinov2-small")
        command.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.command=="build":
        if args.output.exists():
            parser.error("Output already exists; choose a new index directory")
        rows = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            parser.error("Manifest must be a JSON array")
        references = [Reference(row["landmark_id"], str(args.manifest.parent/row["image_path"])) for row in rows]
        pipeline = LandmarkPipeline.build(references, args.model, args.batch_size, args.device)
        pipeline.save(args.output)
        print(f"Indexed {len(references)} reference images in {args.output}")
    else:
        pipeline = LandmarkPipeline.load(args.index, args.model, args.device)
        print(json.dumps(pipeline.predict(args.image, args.top_k), indent=2))
    if __name__ == "__main__":
        main()