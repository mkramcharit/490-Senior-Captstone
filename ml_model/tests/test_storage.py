from types import SimpleNamespace

import pytest

from landmark_ml.storage import require_space


def test_storage_guard_blocks_large_write(tmp_path, monkeypatch):
    monkeypatch.setattr('landmark_ml.storage.shutil.disk_usage', lambda path: SimpleNamespace(free=6 * 1024 ** 3))
    with pytest.raises(OSError, match='Build paused'):
        require_space(tmp_path, 2 * 1024 ** 3)
    assert (tmp_path / 'storage-warning.json').is_file()


def test_storage_guard_allows_space_and_clears_warning(tmp_path, monkeypatch):
    monkeypatch.setattr('landmark_ml.storage.shutil.disk_usage', lambda path: SimpleNamespace(free=20 * 1024 ** 3))
    (tmp_path / 'storage-warning.json').write_text('previous warning')
    require_space(tmp_path, 2 * 1024 ** 3)
    assert not (tmp_path / 'storage-warning.json').exists()
