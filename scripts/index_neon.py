import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from landmark_ml.indexing import build_from_neon


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--model', default='dinov2-small')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--fetch-size', type=int, default=256)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--landmark-ids', type=int, nargs='+')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    print(json.dumps(build_from_neon(args.output, model_path=args.model, device=args.device,
        fetch_size=args.fetch_size, batch_size=args.batch_size, workers=args.workers,
        limit=args.limit, landmark_ids=args.landmark_ids, resume=args.resume), indent=2))


if __name__ == '__main__':
    main()
