"""Register a quality-checked cold-start model in its explicit local SQLite store."""

from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
import json
from pathlib import Path
from platform import python_version
import re

import joblib
import mlflow
from mlflow import MlflowClient
from mlflow.models import infer_signature
import mlflow.sklearn
import numpy as np

from src.config import MLFLOW_REGISTERED_MODEL_NAME, PROJECT_ROOT
from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, engineer_features
from src.models.check_quality import junit_counts, local_artifact_path, local_tracking_uri, required_checks
from src.models.train import load_training_features
from src.models.train_cold_start import split_by_date


FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
SEGMENT = "ORR_CHIRAG_TO_NEHRU_PLACE_EB"
SHA256 = re.compile(r"[0-9a-f]{64}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _resolve_input(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _verify_pytest(quality: dict, run_dir: Path) -> None:
    path = _resolve_input(quality.get("pytest_xml", str(run_dir / "pytest.xml")))
    _require(sha256(path.read_bytes()).hexdigest() == quality["pytest_xml_sha256"], "The Pytest report changed after quality approval.")
    counts = junit_counts(path)
    _require(counts == quality["pytest"], "The Pytest counts differ from the quality approval.")


def register_checked_model(run_dir: Path) -> dict:
    """Verify approval provenance, register, reload, and only then mark approved."""
    run_dir = run_dir.resolve()
    registration_path = run_dir / "registration.json"
    if registration_path.exists():
        raise FileExistsError(f"Registration already recorded at {registration_path}; choose a new run directory.")
    from src.models.release_integrity import verify_release_reports
    verify_release_reports(run_dir)
    run_bytes = (run_dir / "run_report.json").read_bytes()
    run = json.loads(run_bytes)
    quality = json.loads((run_dir / "quality_report.json").read_bytes())
    checks = quality.get("checks")
    _require(quality.get("quality_gate_passed") is True and isinstance(checks, dict) and bool(checks) and all(value is True for value in checks.values()), "Every quality check must pass before registration.")
    _require(sha256(run_bytes).hexdigest() == quality.get("run_report_sha256"), "The training report changed after quality approval.")
    _verify_pytest(quality, run_dir)
    candidate = run["tree_candidate"]
    _require(candidate in ("Random Forest Regressor", "Gradient Boosting Regressor") and candidate == run["selected_by_validation_mae"] == quality["candidate"], "The approved candidate differs from validation selection.")
    _require(required_checks(candidate).issubset(checks), "The approval omits required quality checks.")
    run_id = run["mlflow_run_ids"][candidate]
    digest = quality["candidate_joblib_sha256"]
    _require(isinstance(digest, str) and SHA256.fullmatch(digest) is not None and run_id == quality["candidate_run_id"], "The approved training run or artifact hash differs.")
    scope = quality["demo_scope"]
    _require(scope["assessment"] == "historical_demo_only" and scope["segment_id"] == SEGMENT and scope["route_id"] == "90", "Registration is limited to the approved historical Route 90 scope.")
    runtime = {"python": python_version(), **{name: version(name) for name in ("scikit-learn", "pandas", "numpy", "mlflow")}}
    _require(run["runtime"] == quality["runtime"] == runtime, "The current runtime differs from the approved training environment.")
    _require(run["history_policy"] == "cold_start_v1" and run["features"] == FEATURES, "The approved feature schema or history policy differs.")
    sources = quality.get("working_tree_source_sha256")
    critical_sources = {"src/features/build_features.py", "src/models/train.py", "src/models/train_cold_start.py", "src/models/check_quality.py"}
    _require(isinstance(sources, dict) and critical_sources.issubset(sources), "Approval is missing the evaluated source hashes.")
    for relative, approved_hash in sources.items():
        path = (PROJECT_ROOT / relative).resolve()
        _require(path.is_relative_to(PROJECT_ROOT) and sha256(path.read_bytes()).hexdigest() == approved_hash, f"Evaluated source changed after approval: {relative}.")
    for key in ("split_counts", "split_dates_ist", "validation_metrics", "test_metrics"):
        _require(run[key] == quality[key], f"The approved {key} differ from the training report.")

    input_path = _resolve_input(run["traversals"])
    _require(sha256(input_path.read_bytes()).hexdigest() == run["traversals_sha256"] == quality["input_sha256"], "Training input changed after approval.")
    splits = split_by_date(load_training_features(input_path), date.fromisoformat(run["validation_start_ist"]), date.fromisoformat(run["test_start_ist"]))
    _require({name: len(split) for name, split in zip(("train", "validation", "test"), splits)} == run["split_counts"], "The reproduced split sizes differ.")
    test = engineer_features(splits[2], use_observed_history=False)
    demo_rows = (test["segment_id"] == SEGMENT) & (test["route_id"] == "90")
    _require(int(demo_rows.sum()) == scope["held_out_traversals"] and demo_rows.sum() >= 2, "The approved historical demo sample differs from the held-out input.")
    features = test[FEATURES]
    _require(run["model_files"][candidate] == "tree_candidate.joblib", "Expected the candidate artifact to be tree_candidate.joblib.")
    model_bytes = (run_dir / "tree_candidate.joblib").read_bytes()
    _require(sha256(model_bytes).hexdigest() == digest, "Candidate artifact changed after approval.")
    uri = local_tracking_uri(run["mlflow_tracking_uri"])
    client = MlflowClient(tracking_uri=uri, registry_uri=uri)
    training_run = client.get_run(run_id)
    _require(training_run.info.status == "FINISHED", "The selected training run must be completed.")
    _require(training_run.data.params.get("traversals_sha256") == run["traversals_sha256"] and training_run.data.params.get("history_policy") == "cold_start_v1", "The logged training run does not match the approved input and policy.")
    logged_path = local_artifact_path(training_run.info.artifact_uri, "tree_candidate.joblib")
    _require(sha256(logged_path.read_bytes()).hexdigest() == digest, "Logged artifact differs from the approved candidate.")
    # Only deserialize the locally generated artifact after all provenance checks.
    model = joblib.load(BytesIO(model_bytes))
    _require(list(getattr(model, "feature_names_in_", ())) == FEATURES, "The fitted candidate schema differs from serving.")
    expected = np.asarray(model.predict(features), dtype=float)
    _require(expected.shape == (len(features),) and np.isfinite(expected).all() and (expected > 0).all(), "The approved model returned invalid held-out durations.")
    _require(mlflow.active_run() is None, "Finish the active MLflow run before registering a checked model.")

    old_tracking = mlflow.get_tracking_uri()
    old_registry = mlflow.get_registry_uri()
    registered = None
    created_report = False
    try:
        mlflow.set_tracking_uri(uri)
        mlflow.set_registry_uri(uri)
        # Reuse the selected training run so the registry points to its provenance.
        with mlflow.start_run(run_id=run_id):
            info = mlflow.sklearn.log_model(
                model, name="quality_checked_model", signature=infer_signature(features, expected),
                input_example=features.head(2),
                pip_requirements=[f"scikit-learn=={runtime['scikit-learn']}", f"pandas=={runtime['pandas']}", f"numpy=={runtime['numpy']}", f"joblib=={version('joblib')}"],
            )
        registered = mlflow.register_model(info.model_uri, MLFLOW_REGISTERED_MODEL_NAME, await_registration_for=60)
        observed = client.get_model_version(registered.name, registered.version)
        _require(observed.status == "READY" and observed.run_id == run_id, "The registered version is not READY or points to another training run.")
        model_uri = f"models:/{registered.name}/{registered.version}"
        reloaded = mlflow.sklearn.load_model(model_uri)
        predictions = np.asarray(reloaded.predict(features), dtype=float)
        _require(predictions.shape == expected.shape and np.isfinite(predictions).all() and (predictions > 0).all() and np.allclose(predictions, expected, rtol=0, atol=1e-8), "The registered model does not reproduce the approved held-out predictions.")
        tags = {"joblib_sha256": digest, "demo_route": "90", "demo_segment": SEGMENT, "quality_gate": "passed_historical_demo",
                'quality_report_sha256': sha256((run_dir / 'quality_report.json').read_bytes()).hexdigest(),
                'run_report_sha256': quality['run_report_sha256'],
                'dependency_lock_sha256': quality['environment_identity']['dependency_lock_sha256']}
        for key, value in tags.items():
            client.set_model_version_tag(registered.name, registered.version, key, value)
        observed = client.get_model_version(registered.name, registered.version)
        _require(all(observed.tags.get(key) == value for key, value in tags.items()), "The registered version did not retain the approval tags.")
        record = {
            "model_name": observed.name, "version": int(observed.version), "status": observed.status,
            "tracking_uri": uri, "model_uri": model_uri, "source_model": info.model_uri,
            "training_run_id": run_id, "joblib_sha256": digest,
            "quality_report": "quality_report.json", "approved_scope": scope["assessment"],
            "verified_predictions": len(features),
            'registry_uri': uri, 'approval_schema_version': 2,
            'quality_report_sha256': tags['quality_report_sha256'],
            'run_report_sha256': tags['run_report_sha256'],
            'dependency_lock_sha256': tags['dependency_lock_sha256'],
        }
        with registration_path.open("x", encoding="utf-8") as stream:
            created_report = True
            stream.write(json.dumps(record, indent=2) + "\n")
        return record
    except Exception:
        if created_report:
            registration_path.unlink(missing_ok=True)
        if registered is not None:
            # Keep a failed new version visible for diagnosis without an approval marker.
            client.set_model_version_tag(registered.name, registered.version, "quality_gate", "failed_registration")
        raise
    finally:
        mlflow.set_tracking_uri(old_tracking)
        mlflow.set_registry_uri(old_registry)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = register_checked_model(args.run_dir)
    except Exception as exc:
        parser.exit(1, f"Model registration failed: {exc}\n")
    print(f"Registered {record['model_name']} v{record['version']} after verifying {record['verified_predictions']} held-out predictions.")


if __name__ == "__main__":
    main()
