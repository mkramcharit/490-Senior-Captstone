import hashlib
import json
from pathlib import Path
import zipfile


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return sha256_stream(stream)


def sha256_stream(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def verify_bundle(directory):
    directory = Path(directory)
    path = directory / 'ml-version.json'
    if not path.is_file():
        return {'checksums_verified': False, 'reason': 'No checksum manifest supplied.'}
    manifest = json.loads(path.read_text(encoding='utf-8'))
    files = manifest.get('files')
    if manifest.get('version') != 1 or not isinstance(files, dict) or not {'images.faiss', 'references.json'} <= files.keys():
        raise ValueError('Invalid ML bundle manifest')
    for name, expected in files.items():
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Invalid bundle filename')
        candidate = directory / name
        if not candidate.is_file() or sha256_file(candidate) != expected:
            raise ValueError(f'Bundle checksum mismatch: {name}')
    for name in ('calibration.json', 'recognition-policy.json'):
        if (directory / name).exists() and name not in files:
            raise ValueError(f'Unverified runtime configuration: {name}')
    return {'checksums_verified': True, 'files_verified': len(files)}


def inspect_pipeline(pipeline):
    from dataclasses import asdict
    directory = Path(pipeline.index_directory) if pipeline.index_directory else None
    return {
        'index_directory': str(directory) if directory else None,
        'model_directory': str(pipeline.embedder.model_path),
        'model_signature': pipeline.embedder.signature,
        'reference_count': pipeline.index.index.ntotal,
        'landmark_count': pipeline.indexed_landmark_count,
        'dimension': pipeline.index.index.d,
        'index_type': type(pipeline.index.index).__name__,
        'recognition_policy': asdict(pipeline.recognition_policy),
        'calibration_installed': pipeline.calibrator is not None,
        'confidence_available': pipeline.calibrator is not None,
        'confidence_scope': pipeline.calibrator.get('validation_scope', pipeline.calibrator.get('dataset')) if pipeline.calibrator else None,
        'integrity': verify_bundle(directory) if directory else None,
    }


def package_bundle(directory, output, pipeline):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    if pipeline.index_directory is None or Path(pipeline.index_directory).resolve() != directory:
        raise ValueError('The inspected pipeline must match the exported directory')
    verify_bundle(directory)
    names = ['images.faiss', 'references.json']
    names += [name for name in ('calibration.json', 'recognition-policy.json', 'build.json', 'validation.json') if (directory / name).is_file()]
    manifest = {'version': 1, 'files': {name: sha256_file(directory / name) for name in names},
                'inspection': inspect_pipeline(pipeline)}
    output.parent.mkdir(parents=True, exist_ok=True)
    from .storage import require_space
    require_space(output.parent, sum((directory / name).stat().st_size for name in names))
    temporary = output.with_name(output.name + '.pending')
    if temporary.exists():
        raise FileExistsError(temporary)
    try:
        with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for name in names:
                archive.write(directory / name, name)
            archive.writestr('ml-version.json', json.dumps(manifest, indent=2))
        with zipfile.ZipFile(temporary) as archive:
            for name, digest in manifest['files'].items():
                with archive.open(name) as stream:
                    if sha256_stream(stream) != digest:
                        raise ValueError(f'Export validation failed: {name}')
        temporary.rename(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'output': str(output), 'size_bytes': output.stat().st_size,
            'sha256': sha256_file(output), 'reference_count': pipeline.index.index.ntotal,
            'landmark_count': pipeline.indexed_landmark_count}
