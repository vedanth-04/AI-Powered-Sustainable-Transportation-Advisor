"""Capture verifiable source, environment and optional DVC identities for new runs."""

from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys

import yaml

from src.config import PROJECT_ROOT as ROOT

SOURCES = ('src/config.py', 'src/features/build_features.py', 'src/features/segment_config.py',
           'src/models/train.py', 'src/models/train_cold_start.py', 'src/models/check_quality.py',
           'src/models/register_checked_model.py', 'src/models/export_serving_bundle.py',
           'src/models/provenance.py', 'src/models/release_integrity.py',
           'src/models/baseline.py', 'src/models/evaluate.py',
           'src/api/bundle.py', 'src/api/main.py', 'scripts/verify_environment.py')


def file_hash(path: Path) -> str:
    value = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def source_identity() -> dict:
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=10).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True, timeout=10)
    return {'git_head': head, 'source_worktree_dirty': bool(status.strip()),
            'working_tree_source_sha256': {name: file_hash(ROOT / name) for name in SOURCES}}


def environment_identity() -> dict:
    from scripts.verify_environment import verify
    lock = ROOT / 'requirements-dev.lock.txt'
    checked = verify(lock)
    if not checked['passed']:
        raise ValueError('Release environment differs from the development lock; run scripts.verify_environment.')
    consistency = subprocess.run([sys.executable, '-m', 'pip', 'check'], capture_output=True, text=True, timeout=60)
    if consistency.returncode:
        raise ValueError('Release environment fails pip check; inspect it separately before approval.')
    return {'dependency_lock_sha256': file_hash(lock),
            'model_runtime': {name: version(name) for name in ('scikit-learn', 'numpy', 'pandas', 'scipy', 'joblib')}}


def data_identity(traversals: Path, lineage_path: Path | None) -> dict:
    identity = {'kind': 'sha256_only', 'input_sha256': file_hash(traversals)}
    if lineage_path is None:
        return identity
    lineage = json.loads(lineage_path.read_bytes())
    if lineage.get('lineage_version') != 1 or not lineage.get('sources_sha256'):
        raise ValueError('Data lineage requires a supported schema and evaluated source hashes.')
    if identity['input_sha256'] not in (lineage.get('traversals_sha256'), lineage.get('features_sha256')):
        raise ValueError('Data lineage does not identify this training input.')
    raw = lineage['raw']
    pointer = (ROOT / raw['pointer']).resolve()
    if not pointer.is_relative_to(ROOT) or pointer.suffix != '.dvc':
        raise ValueError('Data pointer must be inside this repository.')
    record = yaml.safe_load(pointer.read_bytes())['outs'][0]
    if file_hash(pointer) != raw['pointer_sha256'] or record['md5'] != raw['dvc_md5']:
        raise ValueError('DVC pointer differs from the data lineage.')
    raw_path = (ROOT / raw['path']).resolve()
    if not raw_path.is_relative_to(ROOT) or pointer.parent / record['path'] != raw_path:
        raise ValueError('Raw data path differs from its pointer.')
    from src.data.prepare_sample import digest
    if file_hash(raw_path) != raw['sha256'] or digest(raw_path, 'md5') != raw['dvc_md5']:
        raise ValueError('Raw data bytes differ from the data lineage.')
    lock_path = ROOT / 'dvc.lock'
    stages = yaml.safe_load(lock_path.read_bytes())['stages'].values()
    input_md5 = digest(traversals, 'md5')
    # Require a committed-pipeline output, not merely an arbitrary CSV + claimed raw ID.
    if not any(item.get('md5') == input_md5 and (ROOT / item['path']).resolve() == traversals.resolve()
               for stage in stages for item in stage.get('outs', [])):
        raise ValueError('Training input is not an output identified by dvc.lock.')
    if lineage['dependency_lock_sha256'] != file_hash(ROOT / 'requirements-dev.lock.txt'):
        raise ValueError('Data preparation dependency lock changed.')
    for name, digest_value in lineage['sources_sha256'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or file_hash(path) != digest_value:
            raise ValueError('Data preparation source changed after processing.')
    return {**identity, 'kind': 'dvc', 'raw_dvc_md5': raw['dvc_md5'],
            'raw_sha256': raw['sha256'], 'pointer_sha256': raw['pointer_sha256'],
            'lineage_sha256': file_hash(lineage_path), 'dvc_lock_sha256': file_hash(lock_path)}
