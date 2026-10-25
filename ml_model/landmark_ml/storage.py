import json
import os
import shutil
import threading
from pathlib import Path


allocation_lock = threading.Lock()


def require_space(directory, additional_bytes=0):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    checks = [(directory, 5 * 1024 ** 3 + max(0, additional_bytes))]
    if os.name == 'nt' and directory.anchor.lower() != 'c:\\':
        checks.append((Path('C:/'), 3 * 1024 ** 3))
    for location, required in checks:
        free = shutil.disk_usage(location).free
        if free < required:
            report = {'phase': 'storage_paused', 'drive': str(location.anchor),
                      'free_bytes': free, 'required_free_bytes': required,
                      'build_directory': str(directory)}
            (directory / 'storage-warning.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            raise OSError(f'Build paused to protect free space: {location.anchor} has {free} bytes; {required} required')
    (directory / 'storage-warning.json').unlink(missing_ok=True)
