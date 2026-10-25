import argparse
import json
import os
from pathlib import Path
import sys
import unicodedata

from dotenv import load_dotenv
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ml_model'))
from landmark_ml.embeddings import DinoV2Embedder
from landmark_ml.indexing import export_index
from landmark_ml.retrieval import Reference, ReferenceIndex
from landmark_ml.storage import require_space


def normalized_name(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value or '').casefold() if c.isalnum())


def verify_catalog_record(database_url, landmark_id, expected_name, expected_category):
    with psycopg.connect(database_url, connect_timeout=15) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        connection.execute('SET statement_timeout=20000')
        rows = connection.execute('SELECT DISTINCT name,category_name FROM public.training_data WHERE landmark_id=%s', (landmark_id,)).fetchall()
    if not rows:
        raise ValueError('No existing Neon record for this landmark ID; ask the database teammate to add it first')
    names = {normalized_name(expected_name), normalized_name(expected_category)} - {''}
    if not any(normalized_name(name) in names or normalized_name(category) in names for name, category in rows):
        raise ValueError('Neon landmark identity does not match the requested reference collection')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('index', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--landmark-id', type=int, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--category', default='')
    parser.add_argument('--model', default='dinov2-small')
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory; the existing index is preserved')
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    verify_catalog_record(os.environ['DATABASE_URL'], args.landmark_id, args.name, args.category)
    rows = json.loads(args.manifest.read_text(encoding='utf-8'))
    if not rows:
        parser.error('Reference collection is empty')
    references = []
    for row in rows:
        if row.get('landmark_id') not in (None, args.landmark_id):
            raise ValueError('Manifest contains a different landmark ID')
        path = (args.manifest.parent / row['image_path']).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        references.append(Reference(args.landmark_id, str(path)))
    embedder = DinoV2Embedder(args.model, args.device)
    index = ReferenceIndex.load(args.index, embedder.signature)
    vectors = embedder.embed([row.image_path for row in references])
    index.add(vectors, references)
    require_space(args.output.parent, sum(p.stat().st_size for p in args.index.iterdir() if p.is_file() and p.name != 'landmarks.index'))
    export_index(index, args.output)
    report = {'reference_count': index.index.ntotal, 'landmark_count': len({r.landmark_id for r in index.references}),
              'added_references': len(references), 'landmark_id': args.landmark_id, 'confidence_calibrated': False,
              'source_index': str(args.index.resolve()), 'source_manifest': str(args.manifest.resolve())}
    (args.output / 'coverage-update.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
