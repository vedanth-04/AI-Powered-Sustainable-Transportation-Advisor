"""Run tests, historical training, quality approval, registration and bundle checks locally."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_exported_api(bundle_dir: Path) -> dict:
    """Exercise the newly exported artifact in process, without changing the live API."""
    from fastapi.testclient import TestClient
    from src.api.main import create_app

    request = {
        "segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB",
        "route_id": "90",
        "entry_at": "2019-07-08T17:10:00+05:30",
    }
    with TestClient(create_app(bundle_dir)) as client:
        health = client.get("/health")
        prediction = client.post("/predict/bus", json=request)
        rejection = client.post("/predict/bus", json={**request, "route_id": "999"})
        if (health.status_code, prediction.status_code, rejection.status_code) != (200, 200, 422):
            raise ValueError("The exported bundle did not pass readiness, prediction and route validation.")
        if health.json()["model_version"] != prediction.json()["model_version"]:
            raise ValueError("Readiness and prediction reported different model versions.")
    return {
        "kind": "in_process_api_check",
        "request": request,
        "health": health.json(),
        "prediction": prediction.json(),
        "unsupported_route_status": rejection.status_code,
    }


def reproduce(traversals: Path, validation_start: date, test_start: date, output_dir: Path, *, data_lineage: Path | None = None, allow_unversioned_data: bool = False) -> dict:
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Run this workflow in the Python 3.12 release/test environment.")
    traversals = traversals.resolve(strict=True)
    if not traversals.is_file():
        raise ValueError("--traversals must name a local CSV file.")
    if validation_start >= test_start:
        raise ValueError("Validation must start before testing.")
    output_dir = output_dir.resolve()
    # A new root isolates every run, including its SQLite registry and serving bundle.
    output_dir.mkdir(parents=True, exist_ok=False)
    run_dir = output_dir / "training"
    bundle_dir = output_dir / "serving"
    tracking_db = output_dir / "registry" / "tracking.db"
    junit = output_dir / "pytest.xml"
    report_path = output_dir / "workflow_report.json"
    report = {
        "started_at_utc": utc_now(),
        "status": "running",
        "scope": "isolated_historical_reproduction",
        "input_sha256": sha256(traversals.read_bytes()).hexdigest(),
        "validation_start_ist": validation_start.isoformat(),
        "test_start_ist": test_start.isoformat(),
        "stages": {},
    }

    def save() -> None:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def stage(name, action):
        report["current_stage"] = name
        record = {"status": "running", "started_at_utc": utc_now()}
        report["stages"][name] = record
        save()
        result = action()
        record.update(status="passed", completed_at_utc=utc_now())
        save()
        return result

    try:
        # MLflow test artifacts have nested paths; use a short OS temporary root on Windows.
        pytest_temp = Path(tempfile.mkdtemp(prefix="p2-tests-"))
        report["pytest_temp_dir"] = str(pytest_temp)
        stage("tests", lambda: subprocess.run(
            [sys.executable, "-m", "pytest", str(ROOT / "tests"), "-q",
             f"--junitxml={junit}", f"--basetemp={pytest_temp}"],
            cwd=ROOT, env={**os.environ, "MPLBACKEND": "Agg"},
            check=True, timeout=600,
        ))
        def load_model_steps():
            # Attribute an import failure separately from the completed test stage.
            from src.models.train_cold_start import train_cold_start_models
            from src.models.check_quality import check_model_quality
            from src.models.register_checked_model import register_checked_model
            from src.models.export_serving_bundle import export_serving_bundle
            return (train_cold_start_models, check_model_quality,
                    register_checked_model, export_serving_bundle)

        (train_cold_start_models, check_model_quality,
         register_checked_model, export_serving_bundle) = stage("dependencies", load_model_steps)

        stage("training", lambda: train_cold_start_models(
            traversals, validation_start, test_start, run_dir, tracking_db=tracking_db,
            data_lineage=data_lineage,
        ))
        quality = stage("quality", lambda: check_model_quality(run_dir, junit))
        registration = stage("registration", lambda: register_checked_model(run_dir))
        manifest = stage("export", lambda: export_serving_bundle(run_dir, bundle_dir, allow_unversioned_data=allow_unversioned_data))
        report['release_eligible'] = manifest.provenance.release_eligible
        report["api_check"] = stage("exported_api", lambda: check_exported_api(bundle_dir))
        report.update(
            status="passed", completed_at_utc=utc_now(),
            candidate=quality["candidate"],
            model_name=registration["model_name"], model_version=registration["version"],
            tracking_uri=registration["tracking_uri"], bundle_dir=str(bundle_dir),
        )
        report.pop("current_stage", None)
        save()
    except (Exception, KeyboardInterrupt) as exc:
        name = report.get("current_stage")
        if name:
            report["stages"][name]["status"] = "failed"
        report.update(status="failed", completed_at_utc=utc_now(), error=str(exc))
        save()
        raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traversals", type=Path, required=True)
    parser.add_argument('--data-lineage', type=Path, help='Verified DVC lineage for this exact input.')
    parser.add_argument('--allow-unversioned-data', action='store_true', help='Isolated research reproduction only; does not create an eligible release.')
    parser.add_argument("--validation-start", type=date.fromisoformat, default=date(2019, 7, 5))
    parser.add_argument("--test-start", type=date.fromisoformat, default=date(2019, 7, 8))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / (
        "phase2_reproduction_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f_UTC")
    ))
    args = parser.parse_args()
    try:
        report = reproduce(args.traversals, args.validation_start, args.test_start, args.output_dir, data_lineage=args.data_lineage, allow_unversioned_data=args.allow_unversioned_data)
    except KeyboardInterrupt:
        parser.exit(130, "Workflow interrupted. Partial evidence remains in the new output directory.\n")
    except Exception as exc:
        parser.exit(1, f"Workflow failed: {exc}\n")
    print(f"Historical workflow passed. Evidence: {args.output_dir.resolve() / 'workflow_report.json'}")
    print(f"Exported {report['model_name']} v{report['model_version']} in the isolated local registry.")


if __name__ == "__main__":
    main()
