"""Deterministic DVC preparation of the available daily sample, without training."""

import argparse
import json
from pathlib import Path
import tempfile

import pandas as pd
import yaml

from src.config import PROJECT_ROOT
from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, engineer_features
from src.features.build_labels import generate_all_corridor_labels

ROOT = PROJECT_ROOT
DEST = ROOT / 'data/processed/sample_cold_start'
RAW = ROOT / 'data/raw/2019-07-01.db'
POINTER = ROOT / 'data/raw/2019-07-01.db.dvc'
SOURCES = ('src/config.py', 'src/data/loader.py', 'src/data/cleaner.py',
           'src/features/segment_config.py', 'src/features/label_generation.py',
           'src/features/build_labels.py', 'src/features/build_features.py',
           'src/data/prepare_sample.py')


def digest(path: Path, algorithm: str = 'sha256') -> str:
    import hashlib
    value = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    # Stable ordering, portable newlines and round-trip float serialization.
    frame = frame.sort_values(['t_entry', 'segment_id', 'route_id', 'vehicle_id', 't_exit'], kind='stable')
    frame.to_csv(path, index=False, float_format='%.17g', lineterminator='\n')


def prepare_labels(raw: Path = RAW, pointer: Path = POINTER, destination: Path = DEST) -> dict:
    output = yaml.safe_load(pointer.read_text(encoding='utf-8'))['outs'][0]
    if output.get('path') != raw.name or output.get('hash', 'md5') != 'md5':
        raise ValueError('Expected the daily sample MD5 pointer.')
    if raw.stat().st_size != output['size'] or digest(raw, 'md5') != output['md5']:
        raise ValueError('Raw data does not match its unchanged DVC pointer.')
    destination.mkdir(parents=True, exist_ok=True)
    # Existing generator writes into a disposable workspace, never historical outputs.
    with tempfile.TemporaryDirectory(prefix='p2-labels-') as temporary:
        frame = generate_all_corridor_labels(raw, Path(temporary))
    if frame.empty:
        raise ValueError('No labels: do not record an empty successful pipeline.')
    target = destination / 'traversals.csv'
    write_csv(frame, target)
    lineage = {
        'lineage_version': 1, 'scope': 'one_day_sample_not_637_row_release',
        'raw': {'path': 'data/raw/' + raw.name, 'sha256': digest(raw),
                'dvc_md5': output['md5'], 'size': output['size'],
                'pointer': 'data/raw/' + pointer.name, 'pointer_sha256': digest(pointer)},
        'sources_sha256': {name: digest(ROOT / name) for name in SOURCES},
        'dependency_lock_sha256': digest(ROOT / 'requirements-dev.lock.txt'),
        'traversals_sha256': digest(target), 'rows': len(frame),
        'entry_epoch_range': [float(frame.t_entry.min()), float(frame.t_entry.max())],
    }
    write_json(destination / 'labels.lineage.json', lineage)
    return lineage


def prepare_features(destination: Path = DEST) -> dict:
    lineage = json.loads((destination / 'labels.lineage.json').read_text(encoding='utf-8'))
    source = destination / 'traversals.csv'
    if digest(source) != lineage['traversals_sha256']:
        raise ValueError('Traversal bytes differ from their lineage.')
    frame = pd.read_csv(source, dtype={'route_id': str}, float_precision='round_trip')
    result = engineer_features(frame, use_observed_history=False)
    target = destination / 'features.csv'
    write_csv(result, target)
    record = {**lineage, 'labels_lineage_sha256': digest(destination / 'labels.lineage.json'),
              'history_policy': 'cold_start_v1', 'features': CATEGORICAL_FEATURES + NUMERIC_FEATURES,
              'features_sha256': digest(target)}
    write_json(destination / 'features.lineage.json', record)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('labels', 'features'))
    args = parser.parse_args()
    print(json.dumps(prepare_labels() if args.stage == 'labels' else prepare_features(), indent=2))
