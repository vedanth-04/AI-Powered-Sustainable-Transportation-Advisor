"""Mirror the version ledger into a separate Phase 3 MLflow Model Registry.

The Phase 2 registry (outputs/phase2_registry) and the live v1 release are never touched.
MLflow is optional: if it is unavailable or fails, the ledger stays authoritative and
the failure is recorded instead of hiding it.
"""

from __future__ import annotations

from importlib.metadata import version as package_version
from io import BytesIO
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

EXPERIMENT = "BusTravelTime-Phase3-Lifecycle"
TAG_KEYS = ("status", "change_type", "reason", "parent_version", "history_policy", "feature_schema_sha256")


def tracking_uri(store: Path) -> str:
    return f"sqlite:///{store.resolve().as_posix()}"


def sync_to_mlflow(ledger, registry_dir: Path, features: pd.DataFrame) -> dict:
    """Log one run per ledger version, register it, copy tags and set champion/previous aliases."""
    try:
        import mlflow
        import mlflow.sklearn
        from mlflow import MlflowClient
        from mlflow.models import infer_signature
    except Exception as exc:  # pragma: no cover - depends on the local environment
        return {"status": "skipped", "reason": f"MLflow is not importable here ({type(exc).__name__})."}

    store = registry_dir / "mlflow.db"
    uri = tracking_uri(store)
    old_tracking, old_registry = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    synced = []
    try:
        mlflow.set_tracking_uri(uri)
        mlflow.set_registry_uri(uri)
        client = MlflowClient(tracking_uri=uri, registry_uri=uri)
        experiment = mlflow.get_experiment_by_name(EXPERIMENT)
        experiment_id = experiment.experiment_id if experiment else mlflow.create_experiment(
            EXPERIMENT, (registry_dir / "mlflow-artifacts").resolve().as_uri())
        existing = {int(mv.version) for mv in client.search_model_versions(f"name='{ledger.model_name}'")}
        for record in ledger.versions:
            if record["version"] in existing:
                synced.append({"version": record["version"], "status": "already_registered"})
                continue
            artifact = record.get("artifact")
            if not artifact:
                synced.append({"version": record["version"], "status": "no_artifact"})
                continue
            model = joblib.load(BytesIO((registry_dir.parent / artifact["path"]).read_bytes()))
            example = features.head(2)
            with mlflow.start_run(experiment_id=experiment_id, run_name=f"v{record['version']}-{record['change_type']}") as run:
                mlflow.log_params({
                    "ledger_version": record["version"], "change_type": record["change_type"],
                    "training_dates_ist": ",".join(record["training_window"]["dates_ist"]),
                    "training_rows": record["training_window"]["rows"], "algorithm": record["algorithm"],
                    "history_policy": record["history_policy"],
                })
                for prefix, metrics in (("holdout", record.get("holdout_metrics", {})),):
                    mlflow.log_metrics({f"{prefix}_{k}": float(v) for k, v in metrics.items() if isinstance(v, (int, float))})
                mlflow.set_tags({f"ledger.{key}": str(record.get(key)) for key in TAG_KEYS})
                mlflow.log_dict(record, "ledger_record.json")
                gate = record.get("gate")
                if gate:
                    mlflow.log_dict(gate, "release_gate.json" if gate.get("kind") == "release" else "promotion_gate.json")
                release = record.get("release")
                if release:  # a system release: the model weights plus everything the advisor serves with them
                    mlflow.log_dict(release, "release_manifest.json")
                    mlflow.set_tags({"release.kind": "system_release", "release.fingerprint": release["fingerprint"],
                                     "release.bus_model_version": str(release["components"]["bus_model"]["ledger_version"])})
                info = mlflow.sklearn.log_model(
                    model, name="model", signature=infer_signature(example, np.asarray(model.predict(example))),
                    input_example=example,
                    pip_requirements=[f"scikit-learn=={package_version('scikit-learn')}",
                                      f"pandas=={package_version('pandas')}", f"numpy=={package_version('numpy')}"],
                )
            registered = mlflow.register_model(info.model_uri, ledger.model_name, await_registration_for=60)
            if int(registered.version) != record["version"]:
                raise ValueError(f"MLflow assigned version {registered.version} to ledger version {record['version']}; "
                                 "use a fresh Phase 3 registry directory.")
            for key in TAG_KEYS:
                client.set_model_version_tag(ledger.model_name, registered.version, key, str(record.get(key)))
            client.update_model_version(ledger.model_name, registered.version, description=record.get("reason", ""))
            synced.append({"version": record["version"], "status": "registered", "run_id": run.info.run_id})
        for alias, target in ledger.aliases.items():
            client.set_registered_model_alias(ledger.model_name, alias, str(target))
        aliases = {alias: int(client.get_model_version_by_alias(ledger.model_name, alias).version)
                   for alias in ledger.aliases}
        if aliases != ledger.aliases:
            raise ValueError(f"MLflow aliases {aliases} differ from the ledger {ledger.aliases}.")
        return {"status": "ok", "tracking_uri": f"sqlite:///{store.name}", "store": str(store),
                "experiment": EXPERIMENT, "versions": synced, "aliases": aliases,
                "ui_command": f'mlflow ui --backend-store-uri "{uri}" --port 5002'}
    except Exception as exc:  # pragma: no cover - depends on the local MLflow store
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "versions": synced}
    finally:
        mlflow.set_tracking_uri(old_tracking)
        mlflow.set_registry_uri(old_registry)


def describe(result: dict) -> str:
    return json.dumps(result, indent=2, default=str)
