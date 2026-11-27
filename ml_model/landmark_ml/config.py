from pathlib import Path
import os


def project_root():
    source = Path(__file__).resolve().parents[2]
    if (source / 'pyproject.toml').is_file():
        return source
    return Path.cwd().resolve()


def resolve_model(value=None):
    path = Path(value or os.getenv('LANDMARK_MODEL_PATH', 'dinov2-small')).expanduser()
    return path.resolve() if path.is_absolute() else (project_root() / path).resolve()


def resolve_index(value=None):
    explicit = value or os.getenv('LANDMARK_INDEX_PATH')
    if explicit:
        path = Path(explicit).expanduser()
        return path.resolve() if path.is_absolute() else (project_root() / path).resolve()
    root = project_root()
    candidates = [root / 'artifacts/ML/indexes/full-neon/handoff', root / 'artifacts/full-neon/handoff']
    for path in candidates:
        if (path / 'images.faiss').is_file() and (path / 'references.json').is_file():
            return path.resolve()
    raise FileNotFoundError('No reference index installed. Set LANDMARK_INDEX_PATH to the extracted full index directory.')
