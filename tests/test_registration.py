"""Verify gated registration and real SQLite model reloads in isolated stores."""

from datetime import date, datetime
import json

import mlflow
from mlflow import MlflowClient
import numpy as np
import pandas as pd
import pytest

from src.features.segment_config import SEGMENT_ORR_EASTBOUND
from src.models import register_checked_model as registration
from src.models.check_quality import check_model_quality
from src.models.export_serving_bundle import export_serving_bundle
from src.models.train_cold_start import train_cold_start_models


@pytest.fixture
def checked_run(tmp_path):
    rows = []
    for day in (1, 5, 8):
        for hour in (8, 9, 10, 17, 18, 19):
            entry = datetime.fromisoformat(f"2019-07-{day:02d}T{hour:02d}:10:00+05:30").timestamp()
            duration = 5.0 if hour < 12 else 12.0
            rows.append({
                "segment_id": SEGMENT_ORR_EASTBOUND.segment_id,
                "direction": SEGMENT_ORR_EASTBOUND.direction,
                "segment_length_km": SEGMENT_ORR_EASTBOUND.length_km,
                "route_id": "90", "t_entry": entry,
                "t_exit": entry + duration * 60, "travel_time_minutes": duration,
            })
    traversals = tmp_path / "traversals.csv"
    pd.DataFrame(rows).to_csv(traversals, index=False)
    run_dir = tmp_path / "training"
    report = train_cold_start_models(
        traversals, date(2019, 7, 5), date(2019, 7, 8), run_dir,
        tracking_db=tmp_path / "registry" / "tracking.db",
    )
    junit = run_dir / "pytest.xml"
    junit.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="fixture"/></testsuite>', encoding="utf-8")
    quality = check_model_quality(run_dir, junit)
    return run_dir, report, quality


def test_sqlite_registration_reloads_and_exports_approved_model(checked_run, tmp_path):
    run_dir, report, quality = checked_run
    before = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    record = registration.register_checked_model(run_dir)
    assert (mlflow.get_tracking_uri(), mlflow.get_registry_uri()) == before
    assert record["status"] == "READY" and record["version"] == 1
    assert record["training_run_id"] == quality["candidate_run_id"]
    assert record["verified_predictions"] == 6
    client = MlflowClient(tracking_uri=record["tracking_uri"], registry_uri=record["tracking_uri"])
    version = client.get_model_version(record["model_name"], 1)
    assert version.tags["quality_gate"] == "passed_historical_demo"
    assert version.tags["joblib_sha256"] == quality["candidate_joblib_sha256"]
    manifest = export_serving_bundle(run_dir, tmp_path / "bundle")
    assert manifest.model_sha256 == quality["candidate_joblib_sha256"]
    with pytest.raises(FileExistsError):
        registration.register_checked_model(run_dir)
    assert len(client.search_model_versions(f"name='{record['model_name']}'")) == 1


@pytest.mark.parametrize("change", ["failed-check", "candidate-bytes", "training-report", "pytest-report", "evaluated-source"])
def test_changed_approval_inputs_fail_before_registry_access(checked_run, monkeypatch, change):
    run_dir, _, quality = checked_run
    if change == "failed-check":
        quality["checks"][next(iter(quality["checks"]))] = False
        (run_dir / "quality_report.json").write_text(json.dumps(quality), encoding="utf-8")
    elif change == "evaluated-source":
        quality["working_tree_source_sha256"]["src/features/build_features.py"] = "0" * 64
        (run_dir / "quality_report.json").write_text(json.dumps(quality), encoding="utf-8")
    elif change == "candidate-bytes":
        (run_dir / "tree_candidate.joblib").write_bytes(b"changed artifact")
    elif change == "training-report":
        with (run_dir / "run_report.json").open("a", encoding="utf-8") as stream:
            stream.write("\n")
    else:
        (run_dir / "pytest.xml").write_text('<testsuite tests="1" failures="1"/>', encoding="utf-8")

    def no_registry_access(*args, **kwargs):
        pytest.fail("An unapproved input reached the registry client")

    monkeypatch.setattr(registration, "MlflowClient", no_registry_access)
    with pytest.raises(ValueError):
        registration.register_checked_model(run_dir)
    assert not (run_dir / "registration.json").exists()


def test_failed_registered_reload_is_not_marked_approved(checked_run, monkeypatch):
    run_dir, report, _ = checked_run

    class WrongPredictions:
        def predict(self, features):
            return np.full(len(features), 999.0)

    monkeypatch.setattr(registration.mlflow.sklearn, "load_model", lambda *args, **kwargs: WrongPredictions())
    with pytest.raises(ValueError, match="does not reproduce"):
        registration.register_checked_model(run_dir)
    assert not (run_dir / "registration.json").exists()
    client = MlflowClient(tracking_uri=report["mlflow_tracking_uri"], registry_uri=report["mlflow_tracking_uri"])
    version = client.get_model_version("BusTravelTimePredictor", 1)
    assert version.tags["quality_gate"] == "failed_registration"
    assert "joblib_sha256" not in version.tags
