"""Re-evaluate a local cold-start training run before registry approval."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
import json
import math
from pathlib import Path
from platform import python_version
import subprocess
import sys
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname
import xml.etree.ElementTree as ET

import joblib
from mlflow import MlflowClient
import numpy as np
import pandas as pd

from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, TARGET_COLUMN, engineer_features
from src.features.label_generation import IST_OFFSET
from src.models.evaluate import compute_regression_metrics
from src.models.train import BASELINE_NAME, load_training_features
from src.models.train_cold_start import split_by_date


ROOT = Path(__file__).resolve().parents[2]
DEMO_SEGMENT = "ORR_CHIRAG_TO_NEHRU_PLACE_EB"
DEMO_ROUTE = "90"
METRIC_NAMES = {"mae_minutes", "rmse_minutes", "mape_percent", "r2_score"}
MODEL_NAMES = (BASELINE_NAME, "Random Forest Regressor", "Gradient Boosting Regressor")


def required_checks(candidate: str) -> set[str]:
    """Approval consumers require every check, including both reloaded artifacts."""
    if candidate not in MODEL_NAMES[1:]:
        raise ValueError("Unexpected selected tree model.")
    fixed = {
        "read_input_reports", "release_runtime_matches_training", "pytest_passed",
        "same_input_and_date_splits", "cold_start_features_and_route_dtype",
        "local_tracking_and_recorded_metrics", "candidate_beats_median_on_validation_and_test",
        "demo_route_mae_improves",
    }
    return fixed | {
        f"{name}_{suffix}" for name in (BASELINE_NAME, candidate)
        for suffix in ("logged_artifact_matches", "fitted_schema", "validation_reload_reproduces_scores", "test_reload_reproduces_scores")
    }


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Reports must contain finite JSON numbers.")
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON number: {value}")


def read_run_report(path: Path) -> dict:
    report = json.loads(path.read_bytes(), parse_float=_finite_float, parse_constant=_reject_constant)
    if not isinstance(report, dict):
        raise ValueError("The run report must be a JSON object.")
    return report


def local_tracking_uri(value: object) -> str:
    """Accept an existing local SQLite database, never a configured remote store."""
    if not isinstance(value, str) or not value.startswith("sqlite:///"):
        raise ValueError("Quality approval requires an explicit local SQLite tracking URI.")
    database = value[len("sqlite:///"):]
    if (any(character in database for character in ("?", "#", "@"))
            or database.startswith(("//", "\\\\")) or not Path(database).is_absolute()):
        raise ValueError("The SQLite URI must identify an absolute local database path.")
    if not Path(database).is_file():
        raise ValueError("The SQLite tracking database does not exist.")
    return value


def local_artifact_path(uri: str, filename: str) -> Path:
    parsed = urlsplit(uri)
    if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Training artifacts must use a local file URI.")
    decoded = url2pathname(unquote(parsed.path))
    if decoded.startswith(("//", "\\\\")):
        raise ValueError("Network artifact paths are outside the local approval workflow.")
    if not Path(decoded).is_absolute():
        raise ValueError("The logged artifact directory must be an absolute local path.")
    root = Path(decoded).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError("The logged artifact is missing or outside its local run directory.")
    return path


def junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("Expected a Pytest JUnit testsuite or testsuites document.")
    suites = list(root.iter("testsuite"))
    if any(item.findall("testsuite") and item.findall("testcase") for item in suites):
        raise ValueError("A JUnit aggregate suite must not mix direct testcases with child suites.")
    leaves = [item for item in suites if not item.findall("testsuite")]
    cases = [case for suite in leaves for case in suite.findall("testcase")]
    counts = {key: sum(int(item.attrib[key]) for item in leaves) for key in ("tests", "failures", "errors", "skipped")}
    actual = {"tests": len(cases), **{
        key: sum(case.find(tag) is not None for case in cases)
        for key, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped"))
    }}
    if counts != actual or counts["tests"] < 1 or any(counts[key] for key in ("failures", "errors", "skipped")):
        raise ValueError(f"A nonempty, fully passing Pytest report is required; recorded={counts}, observed={actual}.")
    return counts


def _metrics_match(actual: dict, recorded: dict) -> bool:
    return (
        isinstance(actual, dict) and isinstance(recorded, dict)
        and actual.keys() == recorded.keys() == METRIC_NAMES
        and all(type(value) in (int, float) and math.isfinite(value) for scores in (actual, recorded) for value in scores.values())
        and all(math.isclose(actual[key], recorded[key], rel_tol=1e-9, abs_tol=1e-9) for key in METRIC_NAMES)
    )


def check_model_quality(run_dir: Path, pytest_xml: Path) -> dict:
    """Write a new approval/failure report; failed checks never approve a model."""
    destination = run_dir / "quality_report.json"
    if destination.exists():
        raise FileExistsError(f"Quality evidence already exists at {destination}; choose a new run directory.")
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    runtime = {"python": python_version(), **{key: version(key) for key in ("scikit-learn", "pandas", "numpy", "mlflow")}}
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "quality_gate_passed": False, "checks": {}, "runtime": runtime,
        "pytest_xml": str(pytest_xml.resolve()),
        "limitations": [
            "Evaluation uses historical observations and does not establish current traffic accuracy.",
            "Approval is limited to the Route 90 eastbound historical demonstration.",
            "Current service accuracy and timetable-to-gate mapping remain unevaluated.",
        ],
    }
    stage = "read_input_reports"

    def require(condition: bool, reason: str) -> None:
        if not condition:
            raise ValueError(reason)
        report["checks"][stage] = True

    try:
        run_path = run_dir / "run_report.json"
        run = read_run_report(run_path)
        report["run_report_sha256"] = sha256(run_path.read_bytes()).hexdigest()
        report["pytest_xml_sha256"] = sha256(pytest_xml.read_bytes()).hexdigest()
        candidate = run["tree_candidate"]
        require(candidate in {"Random Forest Regressor", "Gradient Boosting Regressor"}, "Unexpected selected tree model.")
        report.update({key: run[key] for key in ("split_counts", "split_dates_ist", "validation_metrics", "test_metrics")})
        report["candidate"] = candidate
        report["candidate_run_id"] = run["mlflow_run_ids"][candidate]

        stage = "release_runtime_matches_training"
        sklearn_parts = tuple(int(item) for item in runtime["scikit-learn"].split(".")[:2])
        require(sys.version_info[:2] == (3, 12) and sklearn_parts >= (1, 5) and run["runtime"] == runtime,
                "The release runtime must be Python 3.12, scikit-learn >=1.5, and match the training report.")

        stage = "pytest_passed"
        report["pytest"] = junit_counts(pytest_xml)
        report["checks"][stage] = True

        stage = "same_input_and_date_splits"
        traversals_path = Path(run["traversals"])
        if not traversals_path.is_absolute():
            traversals_path = ROOT / traversals_path
        digest = sha256(traversals_path.read_bytes()).hexdigest()
        report["input_sha256"] = digest
        traversals = load_training_features(traversals_path)
        splits = split_by_date(traversals, date.fromisoformat(run["validation_start_ist"]), date.fromisoformat(run["test_start_ist"]))
        counts = {key: len(split) for key, split in zip(("train", "validation", "test"), splits)}
        dates = {
            key: sorted(pd.to_datetime(split["t_entry"], unit="s", utc=True).dt.tz_convert(IST_OFFSET).dt.strftime("%Y-%m-%d").unique().tolist())
            for key, split in zip(counts, splits)
        }
        require(digest == run["traversals_sha256"] and counts == run["split_counts"] and dates == run["split_dates_ist"]
                and len(traversals) - sum(counts.values()) == run["boundary_labels_excluded"],
                "Input hash or chronological split metadata differs from training.")

        stage = "cold_start_features_and_route_dtype"
        features = CATEGORICAL_FEATURES + NUMERIC_FEATURES
        engineered = [engineer_features(split, use_observed_history=False) for split in splits]
        require(run["history_policy"] == "cold_start_v1" and run["features"] == features
                and all(frame["route_id"].map(type).eq(str).all() and frame["hist_completed_count"].eq(0).all() for frame in engineered),
                "The feature schema, route dtype or cold-start history policy differs from serving.")
        _, validation, test = engineered
        demo_mask = test["segment_id"].eq(DEMO_SEGMENT) & test["route_id"].eq(DEMO_ROUTE)
        require(int(demo_mask.sum()) >= 2, "The approved route and segment need at least two held-out traversals.")
        report["demo_scope"] = {
            "assessment": "historical_demo_only", "route_id": DEMO_ROUTE,
            "segment_id": DEMO_SEGMENT, "held_out_traversals": int(demo_mask.sum()), "metrics": {},
        }

        stage = "local_tracking_and_recorded_metrics"
        uri = local_tracking_uri(run["mlflow_tracking_uri"])
        client = MlflowClient(tracking_uri=uri, registry_uri=uri)
        validation_names = set(MODEL_NAMES)
        require(run["validation_metrics"].keys() == validation_names and run["test_metrics"].keys() == {BASELINE_NAME, candidate}
                and run["mlflow_run_ids"].keys() == validation_names and run["model_files"].keys() == {BASELINE_NAME, candidate},
                "Model comparison is missing a candidate, baseline, artifact or MLflow run.")
        tracked = {}
        for name in MODEL_NAMES:
            record = client.get_run(run["mlflow_run_ids"][name])
            tracked[name] = record
            expected_params = {key: str(run[key]) for key in ("history_policy", "validation_start_ist", "test_start_ist", "traversals_sha256")}
            expected_params["random_seed"] = str(run["seed"])
            require(record.info.status == "FINISHED" and record.info.lifecycle_stage == "active"
                    and all(record.data.params.get(key) == value for key, value in expected_params.items()),
                    f"{name}: tracked run status or parameters differ from the training report.")
            for split in ("validation", "test"):
                if name not in run[f"{split}_metrics"]:
                    continue
                scores = run[f"{split}_metrics"][name]
                logged = {key: record.data.metrics.get(f"{split}_{key}") for key in METRIC_NAMES}
                require(_metrics_match(scores, logged), f"{name}: logged {split} metrics differ from the training report.")

        for name in (BASELINE_NAME, candidate):
            stage = f"{name}_logged_artifact_matches"
            filename = run["model_files"][name]
            require(isinstance(filename, str) and Path(filename).name == filename and "/" not in filename and "\\" not in filename,
                    "Model artifacts must have local leaf filenames.")
            model_path = (run_dir / filename).resolve()
            require(model_path.parent == run_dir.resolve(), "The model file is outside the training directory.")
            model_bytes = model_path.read_bytes()
            model_digest = sha256(model_bytes).hexdigest()
            logged_path = local_artifact_path(tracked[name].info.artifact_uri, filename)
            require(sha256(logged_path.read_bytes()).hexdigest() == model_digest, f"{name}: logged and local artifact hashes differ.")
            if name == candidate:
                report["candidate_joblib_sha256"] = model_digest
            model = joblib.load(BytesIO(model_bytes))

            stage = f"{name}_fitted_schema"
            require(list(getattr(model, "feature_names_in_", ())) == features if name == candidate else getattr(model, "segment_col", None) == "segment_id",
                    f"{name}: fitted model feature schema differs from the evaluated schema.")
            for split_name, frame in (("validation", validation), ("test", test)):
                stage = f"{name}_{split_name}_reload_reproduces_scores"
                values = np.asarray(model.predict(frame[features]))
                require(values.shape == (len(frame),) and np.isfinite(values).all() and (values > 0).all(),
                        f"{name}: predictions must be a finite positive vector.")
                scores = compute_regression_metrics(frame[TARGET_COLUMN], values)
                require(_metrics_match(scores, run[f"{split_name}_metrics"][name]), f"{name}: reloaded {split_name} scores differ.")
                if split_name == "test":
                    report["demo_scope"]["metrics"][name] = compute_regression_metrics(test.loc[demo_mask, TARGET_COLUMN], values[demo_mask.to_numpy()])

        stage = "candidate_beats_median_on_validation_and_test"
        best_tree = min(MODEL_NAMES[1:], key=lambda name: run["validation_metrics"][name]["mae_minutes"])
        selected = min(MODEL_NAMES, key=lambda name: run["validation_metrics"][name]["mae_minutes"])
        require(best_tree == candidate == selected == run["selected_by_validation_mae"]
                and run["tree_beats_median_on_validation_and_test"] is True
                and all(run[f"{split}_metrics"][candidate]["mae_minutes"] < run[f"{split}_metrics"][BASELINE_NAME]["mae_minutes"] for split in ("validation", "test")),
                "The tree must be selected on validation and beat the median on validation and test.")
        stage = "demo_route_mae_improves"
        demo_metrics = report["demo_scope"]["metrics"]
        require(demo_metrics[candidate]["mae_minutes"] < demo_metrics[BASELINE_NAME]["mae_minutes"],
                "The candidate does not improve MAE in the approved route and segment.")
        require(report["checks"].keys() == required_checks(candidate) and all(report["checks"].values()),
                "The approval report does not contain the complete required checks.")
        report["quality_gate_passed"] = True
        from src.models.provenance import data_identity, environment_identity, source_identity
        report.update(source_identity())
        report['features'] = run['features']
        report['approval_schema_version'] = 2
        report['environment_identity'] = environment_identity()
        lineage_path = Path(run['data_lineage_file']) if run.get('data_lineage_file') else None
        report['data_identity'] = data_identity(traversals_path, lineage_path)
        if run.get('data_identity', report['data_identity']) != report['data_identity']:
            raise ValueError('Training data provenance changed before approval.')
        report['split_row_indices'] = {name: [int(index) for index in split.index]
                                       for name, split in zip(('train', 'validation', 'test'), splits)}
        if run.get('split_row_indices', report['split_row_indices']) != report['split_row_indices']:
            raise ValueError('Training split membership differs from approval.')
        training_provenance = run.get('training_provenance')
        if training_provenance and any(training_provenance[key] != report[key] for key in ('git_head', 'working_tree_source_sha256')):
            raise ValueError('Training source differs from evaluated approval source.')
    except Exception as exc:
        report["quality_gate_passed"] = False
        report["checks"][stage] = False
        report["failed_check"] = stage
        report["failure_reason"] = str(exc)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if not report["quality_gate_passed"]:
        raise ValueError(f"Quality gate failed at {stage}: {report['failure_reason']}. Evidence: {destination}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--pytest-xml", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = check_model_quality(args.run_dir, args.pytest_xml)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Quality gate passed for {report['candidate']}. Report: {args.run_dir / 'quality_report.json'}")


if __name__ == "__main__":
    main()
