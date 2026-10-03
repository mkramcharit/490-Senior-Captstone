import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

from calibrate_confidence import fingerprints


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--exclude", type=Path, nargs="+", required=True)
    parser.add_argument("--landmark-ids", type=int, nargs="+", required=True)
    parser.add_argument("--per-landmark", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261003)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.resume:
        parser.error("Choose a new directory or use --resume")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    excluded_ids, excluded_urls, seen = set(), set(), []
    for manifest in args.exclude:
        for row in json.loads(manifest.read_text(encoding="utf-8")):
            excluded_ids.add(row.get("id"))
            excluded_urls.add(row.get("source_url"))
            seen.append(fingerprints(manifest.parent / row["image_path"]))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "images").mkdir(exist_ok=True)
    collection = args.output / "collection.json"
    rows = json.loads(collection.read_text()) if collection.exists() else []
    failures_path = args.output / "failures.json"
    failures = json.loads(failures_path.read_text()) if failures_path.exists() else []
    attempted = {r["id"] for r in rows + failures}
    seen.extend(fingerprints(args.output / r["image_path"]) for r in rows)
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout=30000")
        candidates = conn.execute("SELECT id,url,landmark_id,name FROM public.training_data WHERE landmark_id = ANY(%s) AND url IS NOT NULL ORDER BY id", (args.landmark_ids,)).fetchall()
    rng = random.Random(args.seed)
    rng.shuffle(candidates)
    for row in candidates:
        key = row["landmark_id"]
        if row["id"] in attempted or row["id"] in excluded_ids or row["url"] in excluded_urls:
            continue
        if sum(r["landmark_id"] == key for r in rows) >= args.per_landmark:
            continue
        parsed = urlparse(row["url"])
        if parsed.hostname != "upload.wikimedia.org" or "/commons/" not in parsed.path:
            continue
        tail = parsed.path.split("/commons/", 1)[1]
        if tail.startswith("thumb/") or not tail.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        url = f"https://upload.wikimedia.org/wikipedia/commons/thumb/{tail}/960px-{tail.rsplit('/', 1)[-1]}"
        path = args.output / "images" / (hashlib.sha256(row["id"].encode()).hexdigest()[:20] + ".jpg")
        attempted.add(row["id"])
        try:
            request = Request(url, headers={"User-Agent": "Trekmark-Capstone/0.1 (landmark confidence evaluation)"})
            with urlopen(request, timeout=20) as response:
                data = response.read(10*1024*1024+1)
            if len(data) > 10*1024*1024:
                raise ValueError("Photo exceeds upload limit")
            path.write_bytes(data)
            digest, visual = fingerprints(path)
            if any(digest == previous or (visual ^ other).bit_count() <= 4 for previous, other in seen):
                raise ValueError("Reference/previous-image duplicate or near-duplicate")
            seen.append((digest, visual))
            record = {**row, "source_url": row["url"], "download_url": url, "sha256": digest,
                      "image_path": path.relative_to(args.output).as_posix()}
            del record["url"]
            rows.append(record)
            print(f"Collected {len(rows)}: {key} ({sum(r['landmark_id'] == key for r in rows)}/{args.per_landmark})", flush=True)
        except Exception as exc:
            if path.exists():
                path.unlink()
            failures.append({"id": row["id"], "landmark_id": key, "reason": type(exc).__name__, "status": getattr(exc, "code", None)})
            print(f"Skipped {row['id']}: {type(exc).__name__} {getattr(exc, 'code', '')}", flush=True)
            if isinstance(exc, HTTPError) and exc.code == 429:
                time.sleep(max(30, min(60, int(exc.headers.get("Retry-After", "30")))))
        collection.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        failures_path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
        time.sleep(5)
    calibration, test = [], []
    split_rng = random.Random(args.seed + 1)
    for key in args.landmark_ids:
        group = [r for r in rows if r["landmark_id"] == key]
        split_rng.shuffle(group)
        middle = len(group)//2
        calibration.extend(group[:middle])
        test.extend(group[middle:])
    for name, payload in (("calibration.json", calibration), ("test.json", test)):
        (args.output / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Frozen split: {len(calibration)} calibration and {len(test)} test photos", flush=True)


if __name__ == "__main__":
    main()
