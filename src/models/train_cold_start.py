"""Compare cold-start bus-time models on distinct IST dates."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
from platform import python_version

import joblib
import mlflow
import numpy as np
import pandas as pd

from src.config import OUTPUTS_DIR, RANDOM_SEED
from src.features.build_features import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    engineer_features,
)
from src.features.label_generation import IST_OFFSET
from src.models.evaluate import compute_regression_metrics, compute_stratified_breakdown
from src.models.train import BASELINE_NAME, build_candidate_models, load_training_features


def split_by_date(
    traversals: pd.DataFrame, validation_start: date, test_start: date
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Keep a label in a fitting or selection period only if it finished there."""
    if validation_start >= test_start:
        raise ValueError("Validation must start before testing.")
    validation_cutoff = datetime.combine(validation_start, time.min, tzinfo=IST_OFFSET).timestamp()
    test_cutoff = datetime.combine(test_start, time.min, tzinfo=IST_OFFSET).timestamp()
    ordered = traversals.sort_values("t_entry", kind="stable")
    entries, exits = ordered["t_entry"], ordered["t_exit"]
    durations = ordered[TARGET_COLUMN]
    if (
        not np.isfinite(ordered[["t_entry", "t_exit", TARGET_COLUMN]]).to_numpy().all()
        or (exits <= entries).any()
        or (durations <= 0).any()
    ):
        raise ValueError("Traversals must have finite, ordered timestamps and positive durations.")

    training = ordered.loc[exits < validation_cutoff]
    validation = ordered.loc[(entries >= validation_cutoff) & (exits < test_cutoff)]
    test = ordered.loc[entries >= test_cutoff]
    if min(len(training), len(validation), len(test)) < 2:
        raise ValueError("Training, validation, and test each need at least two traversals.")
    return training, validation, test


def train_cold_start_models(
    traversals_path: Path,
    validation_start: date,
    test_start: date,
    output_dir: Path,
    *,
    tracking_db: Path | None = None,
    data_lineage: Path | None = None,
) -> dict:
    """Fit all candidates, choose on validation, and test that tree against the median."""
    traversals = load_training_features(traversals_path)
    from src.models.provenance import data_identity, environment_identity, source_identity
    provenance = {**source_identity(), **environment_identity(),
                  'data_identity': data_identity(traversals_path, data_lineage)}
    splits = split_by_date(traversals, validation_start, test_start)
    training, validation, test = [
        engineer_features(split, use_observed_history=False) for split in splits
    ]
    feature_columns = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    models = build_candidate_models()

    validation_metrics = {}
    for name, model in models.items():
        model.fit(training[feature_columns], training[TARGET_COLUMN])
        validation_metrics[name] = compute_regression_metrics(
            validation[TARGET_COLUMN], model.predict(validation[feature_columns])
        )

    candidate = min(
        (name for name in models if name != BASELINE_NAME),
        key=lambda name: validation_metrics[name]["mae_minutes"],
    )
    selected = min(models, key=lambda name: validation_metrics[name]["mae_minutes"])
    test_metrics = {}
    test_slices = []
    for name in (BASELINE_NAME, candidate):
        predictions = models[name].predict(test[feature_columns])
        if not np.isfinite(predictions).all() or (predictions <= 0).any():
            raise ValueError(f"{name} returned an invalid travel time.")
        test_metrics[name] = compute_regression_metrics(test[TARGET_COLUMN], predictions)
        evaluated = test.assign(y_true=test[TARGET_COLUMN], y_pred=predictions)
        test_slices.append(
            compute_stratified_breakdown(evaluated, group_col="segment_id").assign(model=name)
        )

    comparison = pd.DataFrame([
        {
            "model": name,
            "validation_mae_minutes": metrics["mae_minutes"],
            "validation_rmse_minutes": metrics["rmse_minutes"],
            "test_mae_minutes": test_metrics.get(name, {}).get("mae_minutes"),
            "test_rmse_minutes": test_metrics.get(name, {}).get("rmse_minutes"),
        }
        for name, metrics in validation_metrics.items()
    ]).sort_values("validation_mae_minutes", kind="stable")

    output_dir.mkdir(parents=True, exist_ok=False)
    comparison.to_csv(output_dir / "model_comparison.csv", index=False)
    pd.concat(test_slices, ignore_index=True).to_csv(output_dir / "test_by_segment.csv", index=False)
    model_files = {
        BASELINE_NAME: output_dir / "historical_median.joblib",
        candidate: output_dir / "tree_candidate.joblib",
    }
    for name, path in model_files.items():
        joblib.dump(models[name], path)

    report = {
        'training_provenance': provenance,
        'data_identity': provenance['data_identity'],
        'data_lineage_file': str(data_lineage.resolve()) if data_lineage else None,
        "history_policy": "cold_start_v1",
        "features": feature_columns,
        "traversals": str(traversals_path),
        "traversals_sha256": sha256(traversals_path.read_bytes()).hexdigest(),
        "validation_start_ist": validation_start.isoformat(),
        "test_start_ist": test_start.isoformat(),
        "split_counts": {"train": len(training), "validation": len(validation), "test": len(test)},
        'split_row_indices': {name: [int(index) for index in split.index]
                              for name, split in zip(('train', 'validation', 'test'), splits)},
        "split_dates_ist": {
            name: sorted(pd.to_datetime(split["t_entry"], unit="s", utc=True)
                         .dt.tz_convert(IST_OFFSET).dt.strftime("%Y-%m-%d").unique().tolist())
            for name, split in zip(("train", "validation", "test"), splits)
        },
        "boundary_labels_excluded": len(traversals) - sum(map(len, splits)),
        "seed": RANDOM_SEED,
        "runtime": {"python": python_version(), **{
            name: version(name) for name in ("scikit-learn", "pandas", "numpy", "mlflow")
        }},
        "tree_candidate": candidate,
        "selected_by_validation_mae": selected,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "tree_beats_median_on_validation_and_test": (
            selected == candidate
            and test_metrics[candidate]["mae_minutes"] < test_metrics[BASELINE_NAME]["mae_minutes"]
        ),
        "model_files": {name: path.name for name, path in model_files.items()},
    }
    # Keep tracking local to this comparison, including on machines configured with a remote URI.
    tracking_uri = (output_dir / "mlruns").resolve().as_uri()
    if tracking_db is not None:
        tracking_db = tracking_db.resolve()
        tracking_db.parent.mkdir(parents=True, exist_ok=True)
        tracking_uri = f"sqlite:///{tracking_db.as_posix()}"
    report["mlflow_tracking_uri"] = tracking_uri

    previous_tracking_uri = mlflow.get_tracking_uri()
    try:
        mlflow.set_tracking_uri(tracking_uri)
        experiment_name = "BusTravelTime-ColdStart"
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            artifact_location = None
            if tracking_db is not None:
                artifact_location = (tracking_db.parent / "artifacts").as_uri()
            experiment_id = mlflow.create_experiment(experiment_name, artifact_location)
        else:
            experiment_id = experiment.experiment_id
        report["mlflow_run_ids"] = {}
        for name in models:
            with mlflow.start_run(experiment_id=experiment_id, run_name=name) as run:
                mlflow.log_params({
                    "history_policy": report["history_policy"],
                    "validation_start_ist": report["validation_start_ist"],
                    "test_start_ist": report["test_start_ist"],
                    "traversals_sha256": report["traversals_sha256"],
                    "random_seed": RANDOM_SEED,
                })
                mlflow.log_metrics({f"validation_{k}": v for k, v in validation_metrics[name].items()})
                if name in test_metrics:
                    mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics[name].items()})
                    mlflow.log_artifact(str(model_files[name]))
                report["mlflow_run_ids"][name] = run.info.run_id
    finally:
        mlflow.set_tracking_uri(previous_tracking_uri)

    (output_dir / "run_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(comparison.to_string(index=False, na_rep="not tested"))
    print(f"Selected by validation MAE: {selected}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traversals", type=Path, required=True)
    parser.add_argument("--validation-start", type=date.fromisoformat, required=True)
    parser.add_argument("--test-start", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR / "phase2_cold_start")
    parser.add_argument("--tracking-db", type=Path, help="Optional local SQLite tracking database.")
    parser.add_argument('--data-lineage', type=Path, help='Verified DVC preparation lineage JSON for this exact input.')
    args = parser.parse_args()
    train_cold_start_models(
        args.traversals, args.validation_start, args.test_start, args.output_dir,
        tracking_db=args.tracking_db,
        data_lineage=args.data_lineage,
    )
