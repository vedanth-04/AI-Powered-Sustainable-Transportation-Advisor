"""Recheck approval evidence before any release artifact is deserialized or exported."""

from importlib.metadata import version
from datetime import date
import json
from pathlib import Path
from platform import python_version

from src.config import PROJECT_ROOT as ROOT
from src.models.check_quality import junit_counts, required_checks
from src.models.provenance import SOURCES, data_identity, environment_identity, file_hash


def verify_release_reports(run_dir: Path) -> tuple[dict, dict]:
    run = json.loads((run_dir / 'run_report.json').read_bytes())
    quality = json.loads((run_dir / 'quality_report.json').read_bytes())
    checks = quality.get('checks')
    candidate = run['tree_candidate']
    if (quality.get('approval_schema_version') != 2 or quality.get('quality_gate_passed') is not True
            or not isinstance(checks, dict) or set(checks) != required_checks(candidate)
            or not all(value is True for value in checks.values())):
        raise ValueError('Release requires the complete current quality approval.')
    if file_hash(run_dir / 'run_report.json') != quality['run_report_sha256']:
        raise ValueError('Training report changed after approval.')
    junit = Path(quality['pytest_xml'])
    junit = junit if junit.is_absolute() else ROOT / junit
    if file_hash(junit) != quality['pytest_xml_sha256'] or junit_counts(junit) != quality['pytest']:
        raise ValueError('Pytest evidence changed after approval.')
    counts = quality['pytest']
    if counts['tests'] <= 0 or any(counts[key] != 0 for key in ('failures', 'errors', 'skipped')):
        raise ValueError('Release requires an entirely passing test report.')
    runtime = {'python': python_version(), **{n: version(n) for n in ('scikit-learn', 'pandas', 'numpy', 'mlflow')}}
    if run['runtime'] != quality['runtime'] or run['runtime'] != runtime:
        raise ValueError('Release runtime differs from approval.')
    if environment_identity() != quality['environment_identity']:
        raise ValueError('Release lock or model runtime changed after approval.')
    sources = quality['working_tree_source_sha256']
    if not set(SOURCES).issubset(sources):
        raise ValueError('Incomplete evaluated source hashes.')
    for name, digest in sources.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or file_hash(path) != digest:
            raise ValueError(f'Evaluated source changed: {name}')
    path = Path(run['traversals'])
    path = path if path.is_absolute() else ROOT / path
    lineage = Path(run['data_lineage_file']) if run.get('data_lineage_file') else None
    identity = data_identity(path, lineage)
    if identity != quality['data_identity'] or identity['input_sha256'] != run['traversals_sha256']:
        raise ValueError('Training data identity changed after approval.')
    if run.get('data_identity', identity) != identity:
        raise ValueError('Training and approval data lineage differ.')
    if (candidate != run['selected_by_validation_mae'] or candidate != quality['candidate']
            or run['mlflow_run_ids'][candidate] != quality['candidate_run_id']
            or run['history_policy'] != 'cold_start_v1'):
        raise ValueError('Approved selection/run/policy differs.')
    for name in ('features', 'split_counts', 'split_dates_ist', 'validation_metrics', 'test_metrics'):
        if run[name] != quality[name]:
            raise ValueError(f'Approval differs on {name}.')
    if file_hash(run_dir / 'tree_candidate.joblib') != quality['candidate_joblib_sha256']:
        raise ValueError('Candidate artifact changed after approval.')
    from src.models.train import load_training_features
    from src.models.train_cold_start import split_by_date
    splits = split_by_date(load_training_features(path), date.fromisoformat(run['validation_start_ist']), date.fromisoformat(run['test_start_ist']))
    membership = {name: [int(index) for index in split.index]
                  for name, split in zip(('train', 'validation', 'test'), splits)}
    if membership != quality['split_row_indices'] or run.get('split_row_indices', membership) != membership:
        raise ValueError('Held-out split membership changed after approval.')
    return run, quality
