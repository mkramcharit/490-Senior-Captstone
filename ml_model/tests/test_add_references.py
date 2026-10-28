import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('add_references', Path(__file__).resolve().parents[2] / 'scripts/add_references.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('rows,accepted', [([], False), ([('Wrong landmark', 'Category:Wrong')], False), ([('Chureito Pagoda', 'Category:Chureito')], True)])
def test_reference_expansion_requires_existing_correct_neon_identity(monkeypatch, rows, accepted):
    calls = []
    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, parameters=None):
            calls.append((query, parameters))
            return self
        def fetchall(self):
            return rows
    monkeypatch.setattr(module.psycopg, 'connect', lambda *args, **kwargs: Connection())
    if accepted:
        module.verify_catalog_record('postgresql://example/db', 123, 'Chureito Pagoda', '')
    else:
        with pytest.raises(ValueError):
            module.verify_catalog_record('postgresql://example/db', 123, 'Chureito Pagoda', '')
    assert calls[0][0] == 'SET TRANSACTION READ ONLY'
    assert calls[-1][1] == (123,)
