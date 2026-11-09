"""Approval must fail when recorded tests, artifacts or model evidence differ."""

from datetime import date, datetime
from hashlib import sha256
from importlib.metadata import version
import json
from platform import python_version
from types import SimpleNamespace

import joblib
import pandas as pd
import pytest

from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, TARGET_COLUMN, engineer_features
from src.features.label_generation import IST_OFFSET
from src.models import check_quality
from src.models.evaluate import compute_regression_metrics
from src.models.train import BASELINE_NAME, build_candidate_models
from src.models.train_cold_start import split_by_date


@pytest.fixture
def trained_run(tmp_path, monkeypatch, request):
    traversals_path = tmp_path / "traversals.csv"
    rows = []
    for day in (1, 2, 3, 5, 8):
        for hour in (8, 10, 12, 14, 16, 18):
            entry = datetime.fromisoformat(f"2019-07-{day:02}T{hour:02}:00:00+05:30").timestamp()
            duration = 2 + hour * 0.7
            rows.append({
                "segment_id": check_quality.DEMO_SEGMENT, "route_id": "90",
                "direction": "EASTBOUND", "segment_length_km": 2.63,
                "t_entry": entry, "t_exit": entry + duration * 60,
                TARGET_COLUMN: duration,
            })
    # The route filter matters: these samples share the segment, but are outside approval.
    rows += [{**item, "route_id": "999"} for item in rows if datetime.fromtimestamp(item["t_entry"], tz=IST_OFFSET).day == 8]
    traversals = pd.DataFrame(rows)
    traversals.to_csv(traversals_path, index=False)
    train, validation, test = [engineer_features(frame, use_observed_history=False) for frame in split_by_date(traversals, date(2019, 7, 5), date(2019, 7, 8))]
    features = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    models = build_candidate_models()
    if getattr(request, 'param', None) == 'losing':
        from sklearn.dummy import DummyRegressor
        for name in models.keys() - {BASELINE_NAME}:
            models[name].set_params(regressor=DummyRegressor(strategy='constant', constant=30.0))
    scores = {}
    for name, model in models.items():
        model.fit(train[features], train[TARGET_COLUMN])
        scores[name] = compute_regression_metrics(validation[TARGET_COLUMN], model.predict(validation[features]))
    candidate = min(models.keys() - {BASELINE_NAME}, key=lambda name: scores[name]["mae_minutes"])
    run_dir = tmp_path / "training"
    run_dir.mkdir()
    logged = tmp_path / "logged"
    logged.mkdir()
    files = {BASELINE_NAME: "historical_median.joblib", candidate: "tree_candidate.joblib"}
    for name, filename in files.items():
        joblib.dump(models[name], run_dir / filename)
        (logged / filename).write_bytes((run_dir / filename).read_bytes())
    database = tmp_path / "tracking.db"
    database.touch()
    run = {
        "history_policy": "cold_start_v1", "features": features,
        "traversals": str(traversals_path), "traversals_sha256": sha256(traversals_path.read_bytes()).hexdigest(),
        "validation_start_ist": "2019-07-05", "test_start_ist": "2019-07-08",
        "split_counts": {"train": 18, "validation": 6, "test": 12},
        "split_dates_ist": {"train": ["2019-07-01", "2019-07-02", "2019-07-03"], "validation": ["2019-07-05"], "test": ["2019-07-08"]},
        "boundary_labels_excluded": 0, "seed": 42,
        "runtime": {"python": python_version(), **{key: version(key) for key in ("scikit-learn", "pandas", "numpy", "mlflow")}},
        "tree_candidate": candidate, "selected_by_validation_mae": candidate,
        "validation_metrics": scores,
        "test_metrics": {name: compute_regression_metrics(test[TARGET_COLUMN], models[name].predict(test[features])) for name in files},
        "tree_beats_median_on_validation_and_test": True, "model_files": files,
        "mlflow_tracking_uri": f"sqlite:///{database.as_posix()}",
        "mlflow_run_ids": {name: str(index) * 32 for index, name in enumerate(models, 1)},
    }
    records = {}
    for name in models:
        metrics = {f"validation_{key}": value for key, value in scores[name].items()}
        if name in files:
            metrics.update({f"test_{key}": value for key, value in run["test_metrics"][name].items()})
        params = {key: str(run[key]) for key in ("history_policy", "validation_start_ist", "test_start_ist", "traversals_sha256")}
        params["random_seed"] = "42"
        records[run["mlflow_run_ids"][name]] = SimpleNamespace(
            info=SimpleNamespace(status="FINISHED", lifecycle_stage="active", artifact_uri=logged.as_uri()),
            data=SimpleNamespace(params=params, metrics=metrics),
        )
    monkeypatch.setattr(check_quality, "MlflowClient", lambda **kwargs: SimpleNamespace(get_run=records.__getitem__))
    run_path = run_dir / "run_report.json"
    run_path.write_text(json.dumps(run), encoding="utf-8")
    junit = tmp_path / "pytest.xml"
    junit.write_text('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"><testcase name="first"/><testcase name="second"/></testsuite></testsuites>', encoding="utf-8")
    return run_dir, junit, run


def test_quality_gate_recomputes_scope_and_preserves_approval(trained_run):
    run_dir, junit, run = trained_run
    result = check_quality.check_model_quality(run_dir, junit)
    assert result["quality_gate_passed"] is True
    assert all(value is True for value in result["checks"].values())
    assert result["demo_scope"]["held_out_traversals"] == 6
    assert result["run_report_sha256"] == sha256((run_dir / "run_report.json").read_bytes()).hexdigest()
    assert result["pytest_xml_sha256"] == sha256(junit.read_bytes()).hexdigest()
    assert result["pytest_xml"] == str(junit.resolve())
    original = (run_dir / "quality_report.json").read_bytes()
    with pytest.raises(FileExistsError):
        check_quality.check_model_quality(run_dir, junit)
    assert (run_dir / "quality_report.json").read_bytes() == original


@pytest.mark.parametrize("tampering", ["artifact", "metrics", "input", "failed-tests", "empty-tests", "remote-store"])
def test_tampering_records_failure_and_never_approves(trained_run, tampering):
    run_dir, junit, run = trained_run
    if tampering == "artifact":
        (run_dir / run["model_files"][run["tree_candidate"]]).write_bytes(b"untrusted changed artifact")
    elif tampering == "metrics":
        run["test_metrics"][run["tree_candidate"]]["mae_minutes"] += 1
    elif tampering == "input":
        run["traversals_sha256"] = "0" * 64
    elif tampering == "failed-tests":
        junit.write_text('<testsuite tests="1" failures="1" errors="0" skipped="0"><testcase name="broken"><failure/></testcase></testsuite>', encoding="utf-8")
    elif tampering == "empty-tests":
        junit.write_text('<testsuite tests="0" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
    else:
        run["mlflow_tracking_uri"] = "https://tracking.example.test"
    (run_dir / "run_report.json").write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(ValueError, match="Quality gate failed"):
        check_quality.check_model_quality(run_dir, junit)
    failure = json.loads((run_dir / "quality_report.json").read_text(encoding="utf-8"))
    assert failure["quality_gate_passed"] is False
    assert failure["checks"][failure["failed_check"]] is False
    assert failure["failure_reason"]


def test_forged_junit_summary_cannot_hide_a_failed_case(tmp_path):
    junit = tmp_path / "pytest.xml"
    junit.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="broken"><failure/></testcase></testsuite>', encoding="utf-8")
    with pytest.raises(ValueError, match="fully passing"):
        check_quality.junit_counts(junit)


@pytest.mark.parametrize("uri", ["https://tracking.example.test", "sqlite:////server/share.db", "sqlite:///relative.db"])
def test_nonlocal_tracking_stores_are_rejected(uri):
    with pytest.raises(ValueError):
        check_quality.local_tracking_uri(uri)


def test_nested_junit_cannot_hide_a_failed_parent_testcase(tmp_path):
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        '<testsuites><testsuite tests="2" failures="1" errors="0" skipped="0">'
        '<testcase name="hidden"><failure/></testcase>'
        '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="good"/></testsuite>'
        '</testsuite></testsuites>', encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must not mix"):
        check_quality.junit_counts(junit)


@pytest.mark.parametrize('trained_run', ['losing'], indirect=True)
def test_recomputed_losing_candidate_cannot_be_approved(trained_run):
    run_dir, junit, _ = trained_run
    with pytest.raises(ValueError, match='candidate_beats_median_on_validation_and_test'):
        check_quality.check_model_quality(run_dir, junit)
    failure = json.loads((run_dir / 'quality_report.json').read_bytes())
    assert failure['quality_gate_passed'] is False
    assert failure['failed_check'] == 'candidate_beats_median_on_validation_and_test'


def test_failed_quality_cli_returns_nonzero(trained_run):
    import subprocess
    import sys
    run_dir, junit, _ = trained_run
    junit.write_text('<testsuite tests="0" failures="0" errors="0" skipped="0"/>')
    result = subprocess.run([sys.executable, '-B', '-m', 'src.models.check_quality',
                             '--run-dir', str(run_dir), '--pytest-xml', str(junit)], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Quality gate failed' in result.stderr
