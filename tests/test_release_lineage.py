"""Verify DVC identity links and fail closed when evidence changes."""

from hashlib import md5, sha256
import json

import pytest
import yaml

from src.models import provenance


@pytest.fixture
def linked_input(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance, 'ROOT', tmp_path)
    raw_dir = tmp_path / 'data/raw'
    raw_dir.mkdir(parents=True)
    raw = raw_dir / 'sample.db'
    raw.write_bytes(b'isolated raw identity fixture')
    pointer = raw_dir / 'sample.db.dvc'
    pointer.write_text(yaml.safe_dump({'outs': [{'path': raw.name, 'md5': md5(raw.read_bytes()).hexdigest(), 'size': raw.stat().st_size}]}))
    source = tmp_path / 'prepare.py'
    source.write_text('# isolated processing identity fixture\n')
    lock = tmp_path / 'requirements-dev.lock.txt'
    lock.write_text('# isolated dependency identity fixture\n')
    csv = tmp_path / 'traversals.csv'
    csv.write_text('route_id,t_entry\n90,1561968000\n')
    (tmp_path / 'dvc.lock').write_text(yaml.safe_dump({'stages': {'fixture': {'outs': [{'path': csv.name, 'md5': md5(csv.read_bytes()).hexdigest()}]}}}))
    lineage = tmp_path / 'lineage.json'
    lineage.write_text(json.dumps({
        'lineage_version': 1, 'traversals_sha256': provenance.file_hash(csv),
        'raw': {'pointer': 'data/raw/sample.db.dvc', 'path': 'data/raw/sample.db',
                'pointer_sha256': provenance.file_hash(pointer), 'sha256': provenance.file_hash(raw),
                'dvc_md5': md5(raw.read_bytes()).hexdigest()},
        'dependency_lock_sha256': provenance.file_hash(lock),
        'sources_sha256': {'prepare.py': provenance.file_hash(source)},
    }))
    return tmp_path, csv, lineage


def test_linked_dvc_identity_contains_actual_hashes(linked_input):
    root, csv, lineage = linked_input
    identity = provenance.data_identity(csv, lineage)
    assert identity['kind'] == 'dvc'
    assert identity['input_sha256'] == sha256(csv.read_bytes()).hexdigest()
    assert identity['dvc_lock_sha256'] == provenance.file_hash(root / 'dvc.lock')
    assert provenance.data_identity(csv, None) == {'kind': 'sha256_only', 'input_sha256': identity['input_sha256']}


@pytest.mark.parametrize('change', ['raw', 'pointer', 'input', 'source', 'lock', 'untracked-output', 'escaping-pointer'])
def test_changed_dvc_lineage_is_rejected(linked_input, change):
    root, csv, lineage = linked_input
    paths = {'raw': root / 'data/raw/sample.db', 'pointer': root / 'data/raw/sample.db.dvc',
             'input': csv, 'source': root / 'prepare.py', 'lock': root / 'requirements-dev.lock.txt'}
    if change in paths:
        with paths[change].open('ab') as stream:
            stream.write(b'\n# changed\n' if change == 'pointer' else b'changed')
    elif change == 'untracked-output':
        (root / 'dvc.lock').write_text('stages: {}\n')
    else:
        record = json.loads(lineage.read_bytes())
        record['raw']['pointer'] = '../outside.db.dvc'
        lineage.write_text(json.dumps(record))
    with pytest.raises((ValueError, KeyError)):
        provenance.data_identity(csv, lineage)
