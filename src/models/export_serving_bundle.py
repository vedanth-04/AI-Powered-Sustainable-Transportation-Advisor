"""Export the checked joblib artifact linked to a numbered MLflow model version."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from mlflow import MlflowClient

from src.api.bundle import BundleManifest, DEFAULT_BUNDLE_DIR
from src.config import MLFLOW_REGISTERED_MODEL_NAME, OUTPUTS_DIR


def export_serving_bundle(release_dir: Path, bundle_dir: Path) -> BundleManifest:
    registration = json.loads((release_dir / "registration.json").read_text(encoding="utf-8"))
    quality = json.loads((release_dir / "quality_report.json").read_text(encoding="utf-8"))
    run = json.loads((release_dir / "run_report.json").read_text(encoding="utf-8"))
    scope = quality["demo_scope"]
    candidate = quality["candidate"]
    run_id = registration["training_run_id"]
    digest = registration["joblib_sha256"]
    if (
        quality["quality_gate_passed"] is not True
        or registration["status"] != "READY"
        or registration["model_name"] != MLFLOW_REGISTERED_MODEL_NAME
        or scope["assessment"] != "historical_demo_only"
        or registration["approved_scope"] != scope["assessment"]
        or run_id != quality["candidate_run_id"]
        or run_id != run["mlflow_run_ids"][candidate]
        or digest != quality["candidate_joblib_sha256"]
    ):
        raise ValueError("Release reports do not describe the same approved model.")

    uri = registration["tracking_uri"]
    if not uri.startswith("sqlite:///"):
        raise ValueError("This exporter requires the local SQLite registry.")
    client = MlflowClient(tracking_uri=uri, registry_uri=uri)
    registered = client.get_model_version(registration["model_name"], registration["version"])
    if (
        registered.status != "READY"
        or registered.run_id != run_id
        or registered.tags.get("joblib_sha256") != digest
    ):
        raise ValueError("The registry version does not match the approved artifact.")

    artifact = Path(client.download_artifacts(run_id, run["model_files"][candidate]))
    model_bytes = artifact.read_bytes()
    if sha256(model_bytes).hexdigest() != digest:
        raise ValueError("The training run's joblib artifact checksum does not match the approval.")

    manifest = BundleManifest(
        model_name=registered.name,
        model_version=int(registered.version),
        history_policy=run["history_policy"],
        features=run["features"],
        model_sha256=digest,
        scikit_learn_version=run["runtime"]["scikit-learn"],
        segment_id=scope["segment_id"],
        route_id=scope["route_id"],
    )
    manifest_path = bundle_dir / "manifest.json"
    model_path = bundle_dir / "model.joblib"
    if bundle_dir.exists():
        if (
            manifest_path.is_file()
            and model_path.is_file()
            and BundleManifest.model_validate_json(manifest_path.read_bytes()) == manifest
            and sha256(model_path.read_bytes()).hexdigest() == digest
        ):
            return manifest
        raise FileExistsError(f"Choose a new bundle directory. Existing files differ at {bundle_dir}")

    bundle_dir.mkdir(parents=True)
    try:
        model_path.write_bytes(model_bytes)
        manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except OSError:
        manifest_path.unlink(missing_ok=True)
        model_path.unlink(missing_ok=True)
        bundle_dir.rmdir()
        raise
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=OUTPUTS_DIR / "phase2_release_check")
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    args = parser.parse_args()
    manifest = export_serving_bundle(args.release_dir, args.bundle_dir)
    print(f"Serving {manifest.model_name} v{manifest.model_version} from {args.bundle_dir}")
