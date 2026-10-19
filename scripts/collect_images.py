import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from dotenv import load_dotenv
from PIL import Image
import psycopg
from psycopg.rows import dict_row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--landmark-ids", type=int, nargs="+", required=True)
    parser.add_argument("--references-per-landmark", type=int, default=5)
    parser.add_argument("--holdouts-per-landmark", type=int, default=2)
    args = parser.parse_args()
    if args.references_per_landmark < 1 or args.holdouts_per_landmark < 1:
        parser.error("Reference and holdout counts must be positive")
    if args.output.exists():
        parser.error("Output already exists; choose a new collection directory")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    references, holdouts, failures, seen = [], [], [], set()
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout = 30000")
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "images").mkdir()
        for landmark_id in dict.fromkeys(args.landmark_ids):
            rows = conn.execute(
                "SELECT id,url,landmark_id,name FROM public.training_data "
                "WHERE landmark_id=%s AND url IS NOT NULL ORDER BY id LIMIT 100", (landmark_id,)
            ).fetchall()
            accepted = 0
            for row in rows:
                if accepted >= args.references_per_landmark + args.holdouts_per_landmark:
                    break
                url = row["url"]
                parsed = urlparse(url)
                if parsed.hostname != "upload.wikimedia.org" or parsed.scheme not in ("http", "https"):
                    failures.append({"id": row["id"], "reason": "Unsupported image host"})
                    continue
                source_url = "https://" + url.split("://", 1)[1]
                parts = parsed.path.split("/commons/", 1)
                if len(parts) != 2 or parts[1].startswith("thumb/"):
                    continue
                tail = parts[1]
                filename = tail.rsplit("/", 1)[-1]
                url = "https://upload.wikimedia.org/wikipedia/commons/thumb/" + tail + "/960px-" + filename
                try:
                    request = Request(url, headers={"User-Agent": "Trekmark-Capstone/0.1 (landmark reference research)"})
                    with urlopen(request, timeout=30) as response:
                        data = response.read(20 * 1024 * 1024 + 1)
                    if len(data) > 20 * 1024 * 1024:
                        raise ValueError("Image exceeds 20 MB")
                    digest = hashlib.sha256(data).hexdigest()
                    if digest in seen:
                        raise ValueError("Duplicate image content")
                    path = args.output / "images" / (hashlib.sha256(str(row["id"]).encode()).hexdigest()[:20] + ".jpg")
                    path.write_bytes(data)
                    try:
                        with Image.open(path) as image:
                            image.verify()
                    except Exception:
                        path.unlink()
                        raise
                    seen.add(digest)
                    record = {**row, "source_url": source_url, "download_url": url, "sha256": digest,
                              "image_path": path.relative_to(args.output).as_posix()}
                    del record["url"]
                    (references if accepted < args.references_per_landmark else holdouts).append(record)
                    accepted += 1
                    print(f"Downloaded landmark {landmark_id}: {accepted}", flush=True)
                except Exception as exc:
                    failures.append({"id": row["id"], "landmark_id": landmark_id, "reason": type(exc).__name__,
                                     "status": exc.code if isinstance(exc, HTTPError) else None})
                    print(f"Skipped {row['id']}: {type(exc).__name__} {getattr(exc, 'code', '')}", flush=True)
                    if isinstance(exc, HTTPError) and exc.code == 429:
                        time.sleep(30)
                for filename, payload in (("manifest.json", references), ("holdouts.json", holdouts), ("download_failures.json", failures)):
                    (args.output / filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")
                time.sleep(3)
            print(f"Landmark {landmark_id}: {accepted} usable images", flush=True)
    for filename, payload in (("manifest.json", references), ("holdouts.json", holdouts), ("download_failures.json", failures)):
        (args.output / filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {len(references)} references and {len(holdouts)} holdouts", flush=True)
    if any(sum(row["landmark_id"] == key for row in references) < args.references_per_landmark
           or sum(row["landmark_id"] == key for row in holdouts) < args.holdouts_per_landmark
           for key in args.landmark_ids):
        raise SystemExit("Collection incomplete; inspect manifests and failures before building")


if __name__ == "__main__":
    main()
