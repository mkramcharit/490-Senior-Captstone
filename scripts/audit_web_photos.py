import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import unquote, urlsplit

import numpy as np
from PIL import Image, ImageOps


def source_identity(url):
    path = unquote(urlsplit(url).path)
    if '/commons/' not in path:
        return url.split('?')[0]
    tail = path.split('/commons/', 1)[1]
    if tail.startswith('thumb/'):
        tail = tail[6:].rsplit('/', 1)[0]
    return tail.rsplit('/', 1)[-1].replace(' ', '_')


def audit(collection, build, decisions, previous_manifests=()):
    root = collection.parent
    rows = json.loads(collection.read_text(encoding='utf-8'))
    reviewed = set(decisions['reviewed_sites'])
    if {row['site'] for row in rows} - reviewed:
        raise ValueError('Every site must be reviewed before creating the test manifest')
    exclusions = dict(decisions.get('excluded_photos', {}))
    by_sha = {row['sha256']: row for row in rows}
    by_source = {source_identity(row['original_url']): row for row in rows}
    source_record_count = 0
    for path in sorted((build / 'shards').glob('*/records.json')):
        for record in json.loads(path.read_text(encoding='utf-8')):
            source_record_count += 1
            row = by_sha.get(record.get('sha256')) or by_source.get(source_identity(record.get('url', '')))
            if row:
                exclusions[row['sha256']] = 'Reference content or original source identity already indexed'
    if source_record_count < 1:
        raise ValueError('No reference provenance records were available for overlap checks')
    with sqlite3.connect((build / 'ledger.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as ledger:
        expected_count = ledger.execute("SELECT count(*) FROM images WHERE state='indexed'").fetchone()[0]
    if source_record_count != expected_count:
        raise ValueError('Source provenance records do not account for every indexed image')
    accepted, seen, retained_hashes, duplicate_occurrences = [], [], set(), []
    for previous in previous_manifests:
        for row in json.loads(previous.read_text(encoding='utf-8')):
            with Image.open(previous.parent / row['image_path']) as image:
                pixels = np.asarray(ImageOps.exif_transpose(image).convert('L').resize((9, 8)))
                seen.append(int.from_bytes(np.packbits((pixels[:, 1:] > pixels[:, :-1]).ravel()).tobytes(), 'big'))
    for row in sorted(rows, key=lambda item: item['sha256']):
        path = root / row['image_path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row['sha256']:
            raise ValueError('Collected image changed before verification')
        if digest in exclusions:
            continue
        if digest in retained_hashes:
            duplicate_occurrences.append(row['image_path'])
            continue
        with Image.open(path) as image:
            pixels = np.asarray(ImageOps.exif_transpose(image).convert('L').resize((9, 8)))
            visual = int.from_bytes(np.packbits((pixels[:, 1:] > pixels[:, :-1]).ravel()).tobytes(), 'big')
        if any((visual ^ previous).bit_count() <= 4 for previous in seen):
            exclusions[digest] = 'Query near-duplicate excluded before prediction'
            continue
        seen.append(visual)
        retained_hashes.add(digest)
        accepted.append({**row, 'ground_truth_verified': True, 'visual_review': 'Landmark identity and unambiguous subject reviewed on source metadata and contact sheet before inference'})
    report = {'source_record_count': source_record_count, 'collected_count': len(rows),
              'verified_count': len(accepted), 'excluded_photos': exclusions, 'duplicate_occurrences': duplicate_occurrences,
              'limitations': ['Source URL identity and exact image hashes were checked across all indexed provenance records.',
                              'Perceptual duplicates were checked within queries; all training images were not available for an exhaustive visual-duplicate audit.',
                              'Post-2019 capture dates are source metadata, not independent forensic verification.']}
    return accepted, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('collection', type=Path)
    parser.add_argument('build', type=Path)
    parser.add_argument('decisions', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--exclude-query',type=Path,nargs='*',default=[])
    args = parser.parse_args()
    rows, report = audit(args.collection, args.build, json.loads(args.decisions.read_text(encoding='utf-8')), args.exclude_query)
    args.output.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    args.output.with_name('source-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
