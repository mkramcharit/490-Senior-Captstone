import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import numpy as np
from PIL import Image
import pytest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / 'scripts' / (name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_metadata_values_can_be_numeric_or_html():
    collector = module('collect_web_photos')
    assert collector.plain(2.5) == '2.5'
    assert collector.plain('<a>A &amp; B</a>') == 'A & B'
    assert str(collector.capture_date('Taken on 23 May 2024, 11:16')) == '2024-05-23'
    assert str(collector.capture_date('2023-09-01 08:01:02')) == '2023-09-01'
    assert collector.capture_date('2024-99-99') is None


def test_source_identity_matches_original_and_resized_url():
    audit = module('audit_web_photos')
    original = 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Test%20photo.jpg'
    resized = 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Test_photo.jpg/960px-Test_photo.jpg?test=1'
    assert audit.source_identity(original) == audit.source_identity(resized)


def test_source_audit_removes_reference_overlap_and_requires_complete_provenance(tmp_path):
    audit = module('audit_web_photos')
    build = tmp_path / 'build'
    shard = build / 'shards/one'
    shard.mkdir(parents=True)
    source = 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Reference.jpg'
    (shard / 'records.json').write_text(json.dumps([{'id':'1','url':source,'sha256':'unused'}]))
    with sqlite3.connect(build / 'ledger.sqlite') as connection:
        connection.execute('CREATE TABLE images (state TEXT)')
        connection.execute("INSERT INTO images VALUES ('indexed')")
    rows = []
    rng = np.random.default_rng(8)
    for i in range(2):
        path = tmp_path / f'{i}.jpg'
        Image.fromarray(rng.integers(0,256,(64,64,3),dtype=np.uint8)).save(path)
        rows.append({'site':'test','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                     'original_url':source if i==0 else source.replace('Reference','New'), 'image_path':path.name})
    collection = tmp_path / 'collection.json'
    collection.write_text(json.dumps(rows))
    verified, report = audit.audit(collection, build, {'reviewed_sites':['test']})
    assert len(verified) == 1
    assert verified[0]['ground_truth_verified']
    assert report['source_record_count'] == 1
    collection.write_text(json.dumps(rows+[rows[1]]))
    verified, report = audit.audit(collection, build, {'reviewed_sites':['test']})
    assert len(verified) == 1
    assert report['duplicate_occurrences'] == [rows[1]['image_path']]
    assert verified[0]['sha256'] not in report['excluded_photos']
    with sqlite3.connect(build / 'ledger.sqlite') as connection:
        connection.execute("INSERT INTO images VALUES ('indexed')")
    with pytest.raises(ValueError, match='every indexed image'):
        audit.audit(collection, build, {'reviewed_sites':['test']})
