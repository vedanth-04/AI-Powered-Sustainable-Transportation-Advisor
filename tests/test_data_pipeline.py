"""Regression checks for DVC discovery and genuine deterministic sample processing."""

from hashlib import md5
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

from dvc.repo import Repo
import pytest

from src.data.prepare_sample import prepare_features, prepare_labels


def test_gitignore_keeps_raw_pointer_discoverable(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    Repo.init(str(tmp_path)).close()
    shutil.copyfile(Path(__file__).resolve().parents[1] / '.gitignore', tmp_path / '.gitignore')
    raw = tmp_path / 'data/raw'
    raw.mkdir(parents=True)
    (raw / 'sample.db').write_bytes(b'sample')
    (raw / 'sample.db.dvc').write_text('outs:\n- md5: 5e8ff9bf55ba3508199d22e984129be6\n  size: 6\n  hash: md5\n  path: sample.db\n')
    with Repo(str(tmp_path)) as repo:
        assert len(repo.index.stages) == 1
        assert repo.scm.is_ignored(str(raw / 'sample.db'))
        assert not repo.scm.is_ignored(str(raw / 'sample.db.dvc'))


def test_sample_processing_is_deterministic_and_checks_raw_identity(tmp_path):
    raw = tmp_path / 'sample.db'
    with sqlite3.connect(raw) as conn:
        conn.execute('CREATE TABLE vehicle_feed (vehicle_id TEXT, route_id REAL, trip_id TEXT, timestamp INTEGER, lat REAL, lng REAL, speed REAL, date TEXT, time TEXT)')
        conn.executemany('INSERT INTO vehicle_feed VALUES (?,?,?,?,?,?,?,?,?)', [
            ('TEST', 90.0, 'TRIP', 1561968000 + i * 20, 28.542,
             77.216 + i * 0.0016, 3.0, '2019-07-01', '08:00:00') for i in range(21)
        ])
    pointer = tmp_path / 'sample.db.dvc'
    pointer.write_text(f'outs:\n- md5: {md5(raw.read_bytes()).hexdigest()}\n  size: {raw.stat().st_size}\n  hash: md5\n  path: sample.db\n')
    dest = tmp_path / 'prepared'
    first = prepare_labels(raw, pointer, dest)
    assert first['rows'] > 0
    prepare_features(dest)
    snapshot = {p.name: p.read_bytes() for p in dest.iterdir()}
    prepare_labels(raw, pointer, dest)
    prepare_features(dest)
    assert snapshot == {p.name: p.read_bytes() for p in dest.iterdir()}
    metadata = json.loads((dest / 'features.lineage.json').read_text())
    assert metadata['history_policy'] == 'cold_start_v1'
    assert metadata['raw']['dvc_md5'] == md5(raw.read_bytes()).hexdigest()
    raw.write_bytes(raw.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='DVC pointer'):
        prepare_labels(raw, pointer, dest)
