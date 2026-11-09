"""Export an approved version with current evidence, lineage and prediction parity."""

from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import joblib
import mlflow
from mlflow import MlflowClient
import mlflow.sklearn
import numpy as np

from src.api.bundle import BundleManifest, DEFAULT_BUNDLE_DIR, feature_schema_sha256, load_bundle
from src.config import MLFLOW_REGISTERED_MODEL_NAME, OUTPUTS_DIR, PROJECT_ROOT
from src.features.build_features import engineer_features
from src.models.check_quality import local_tracking_uri
from src.models.provenance import file_hash
from src.models.release_integrity import verify_release_reports
from src.models.train import load_training_features
from src.models.train_cold_start import split_by_date


def _parity(model, features, expected) -> None:
    values = np.asarray(model.predict(features), dtype=float)
    if (values.shape != expected.shape or not np.isfinite(values).all()
            or not (values > 0).all() or not np.allclose(values, expected, rtol=0, atol=1e-8)):
        raise ValueError('Exported/registered model does not reproduce approved held-out predictions.')


def export_serving_bundle(release_dir: Path, bundle_dir: Path, *, allow_unversioned_data: bool = False) -> BundleManifest:
    release_dir = release_dir.resolve()
    run, quality = verify_release_reports(release_dir)
    registration = json.loads((release_dir / 'registration.json').read_bytes())
    scope = quality['demo_scope']
    candidate = quality['candidate']
    run_id = quality['candidate_run_id']
    digest = quality['candidate_joblib_sha256']
    approval_hash = file_hash(release_dir / 'quality_report.json')
    eligible = quality['data_identity']['kind'] == 'dvc' and not quality['source_worktree_dirty']
    if not eligible and not allow_unversioned_data:
        raise ValueError('Release export requires verified DVC lineage and clean source; use --allow-unversioned-data only for isolated research fixtures.')
    expected_tags = {'quality_gate': 'passed_historical_demo', 'joblib_sha256': digest,
                     'quality_report_sha256': approval_hash,
                     'run_report_sha256': quality['run_report_sha256'],
                     'dependency_lock_sha256': quality['environment_identity']['dependency_lock_sha256'],
                     'demo_route': scope['route_id'], 'demo_segment': scope['segment_id']}
    if (registration.get('approval_schema_version') != 2 or registration['status'] != 'READY'
            or registration['model_name'] != MLFLOW_REGISTERED_MODEL_NAME
            or registration['training_run_id'] != run_id or registration['joblib_sha256'] != digest
            or scope['assessment'] != 'historical_demo_only'
            or registration['approved_scope'] != scope['assessment']
            or any(registration.get(k) != expected_tags[k] for k in ('quality_report_sha256', 'run_report_sha256', 'dependency_lock_sha256'))):
        raise ValueError('Registration does not identify the current approval.')
    # Never inherit ambient MLFLOW_* endpoints; shared execution needs a separately
    # provisioned and verified adapter. Remote credentials never enter bundles.
    uri = local_tracking_uri(registration['tracking_uri'])
    if registration.get('registry_uri') != uri or run['mlflow_tracking_uri'] != uri:
        raise ValueError('Tracking and registry URIs must explicitly identify the checked local store.')
    client = MlflowClient(tracking_uri=uri, registry_uri=uri)
    registered = client.get_model_version(registration['model_name'], registration['version'])
    if (registered.status != 'READY' or registered.run_id != run_id
            or any(registered.tags.get(key) != value for key, value in expected_tags.items())):
        raise ValueError('Registry version approval is missing, revoked or mismatched.')
    training_run = client.get_run(run_id)
    if (training_run.info.status != 'FINISHED' or training_run.info.lifecycle_stage != 'active'
            or training_run.data.params.get('traversals_sha256') != run['traversals_sha256']
            or training_run.data.params.get('history_policy') != 'cold_start_v1'):
        raise ValueError('Registered training run is no longer eligible.')
    if run['model_files'][candidate] != 'tree_candidate.joblib':
        raise ValueError('Unexpected model artifact path.')
    model_bytes = Path(client.download_artifacts(run_id, 'tree_candidate.joblib')).read_bytes()
    if sha256(model_bytes).hexdigest() != digest:
        raise ValueError('Training artifact differs from approval.')
    input_path = Path(run['traversals'])
    input_path = input_path if input_path.is_absolute() else PROJECT_ROOT / input_path
    splits = split_by_date(load_training_features(input_path), date.fromisoformat(run['validation_start_ist']), date.fromisoformat(run['test_start_ist']))
    features = engineer_features(splits[2], use_observed_history=False)[run['features']]
    if len(features) != registration['verified_predictions'] or len(features) < 2:
        raise ValueError('Held-out prediction set differs from registration.')
    model = joblib.load(BytesIO(model_bytes))  # Only after all evidence/hash checks.
    expected = np.asarray(model.predict(features), dtype=float)
    _parity(model, features, expected)
    old_tracking, old_registry = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    try:
        mlflow.set_tracking_uri(uri)
        mlflow.set_registry_uri(uri)
        registered_model = mlflow.sklearn.load_model(f'models:/{registered.name}/{registered.version}')
        _parity(registered_model, features, expected)
    finally:
        mlflow.set_tracking_uri(old_tracking)
        mlflow.set_registry_uri(old_registry)
    manifest = BundleManifest(
        manifest_version=2, model_name=registered.name, model_version=int(registered.version),
        history_policy=run['history_policy'], features=run['features'], model_sha256=digest,
        scikit_learn_version=run['runtime']['scikit-learn'], segment_id=scope['segment_id'], route_id=scope['route_id'],
        provenance={
            'training_run_id': run_id, 'source_git_sha': quality['git_head'],
            'source_worktree_dirty': quality['source_worktree_dirty'],
            'source_sha256': quality['working_tree_source_sha256'], 'data': quality['data_identity'],
            'feature_schema_sha256': feature_schema_sha256(),
            'dependency_lock_sha256': expected_tags['dependency_lock_sha256'],
            'quality_report_sha256': approval_hash, 'run_report_sha256': quality['run_report_sha256'],
            'model_runtime': quality['environment_identity']['model_runtime'], 'release_eligible': eligible,
        },
    )
    manifest_bytes = (manifest.model_dump_json(indent=2) + '\n').encode()
    files = {'model.joblib': model_bytes, 'manifest.json': manifest_bytes,
             'environment.lock.txt': (PROJECT_ROOT / 'requirements-dev.lock.txt').read_bytes()}
    if bundle_dir.exists():
        if not all((bundle_dir / name).is_file() and (bundle_dir / name).read_bytes() == contents for name, contents in files.items()):
            raise FileExistsError(f'Choose a new bundle directory; existing files differ at {bundle_dir}')
        _parity(load_bundle(bundle_dir, expected_manifest_sha256=sha256(manifest_bytes).hexdigest()).model, features, expected)
        return manifest
    bundle_dir.mkdir(parents=True)
    try:
        for name, contents in files.items():
            with (bundle_dir / name).open('xb') as stream:
                stream.write(contents)
        _parity(load_bundle(bundle_dir, expected_manifest_sha256=sha256(manifest_bytes).hexdigest()).model, features, expected)
    except Exception:
        for name in files:
            (bundle_dir / name).unlink(missing_ok=True)
        bundle_dir.rmdir()
        raise
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-dir', type=Path, default=OUTPUTS_DIR / 'phase2_release_check')
    parser.add_argument('--bundle-dir', type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument('--allow-unversioned-data', action='store_true', help='Research-only bundle; release_eligible remains false.')
    args = parser.parse_args()
    manifest = export_serving_bundle(args.release_dir, args.bundle_dir, allow_unversioned_data=args.allow_unversioned_data)
    print(f'Exported manifest v2: {manifest.model_name} v{manifest.model_version}; release_eligible={manifest.provenance.release_eligible}')
