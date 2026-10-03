import argparse
import json
from pathlib import Path
import random
import re
from urllib.parse import unquote


def source_group(row):
    name = unquote(row["source_url"].rsplit("/", 1)[-1]).lower()
    if re.search(r"(?:img|dsc)_?\d+", name):
        return str(row["landmark_id"]) + ":" + re.sub(r"(?:img|dsc)_?\d+", "camera-sequence", name)
    if "forest_path_" in name:
        return str(row["landmark_id"]) + ":" + re.sub(r"forest_path_\d+", "forest-path-sequence", name)
    stem = re.sub(r"\.(?:jpg|jpeg|png)$", "", name)
    stem = re.sub(r"[_ -]*\(\d{1,3}\)$", "", stem)
    stem = re.sub(r"[_ -]+\d{1,3}$", "", stem)
    return str(row["landmark_id"]) + ":" + stem


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", type=Path)
    parser.add_argument("--seed", type=int, default=20261004)
    args = parser.parse_args()
    directory = args.collection.parent
    rows = json.loads(args.collection.read_text(encoding="utf-8"))
    exclusions = []
    kept = []
    for row in rows:
        name = unquote(row["source_url"]).lower()
        if "martha_washington_impersonator" in name and "2016" in name:
            exclusions.append({**row, "reason": "Same Martha Washington/Chris Lu event as preliminary test; excluded before model predictions"})
        elif "historic_road_-_flickr_-_gregthebusker" in name:
            exclusions.append({**row, "reason": "Location label could not be verified during pre-prediction visual/source audit"})
        else:
            kept.append({**row, "group_id": source_group(row)})
    rng = random.Random(args.seed)
    calibration, test = [], []
    for key in sorted({r["landmark_id"] for r in kept}):
        groups = {}
        for row in kept:
            if row["landmark_id"] == key:
                groups.setdefault(row["group_id"], []).append(row)
        groups = list(groups.values())
        rng.shuffle(groups)
        groups.sort(key=len, reverse=True)
        first, second = [], []
        for group in groups:
            (first if len(first) <= len(second) else second).extend(group)
        if len(calibration) <= len(test):
            calibration.extend(first)
            test.extend(second)
        else:
            calibration.extend(second)
            test.extend(first)
    for name, payload in (("calibration.json", calibration), ("test.json", test), ("audit_exclusions.json", exclusions)):
        (directory / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Frozen grouped split: {len(calibration)} calibration, {len(test)} test, {len(exclusions)} pre-prediction exclusions")


if __name__ == "__main__":
    main()
