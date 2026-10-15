"""Model training, benchmarking, evaluation, and MLflow tracking pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.config import (
    MLFLOW_EXPERIMENT_NAME,
    MLFLOW_REGISTERED_MODEL_NAME,
    OUTPUTS_DIR,
    PROCESSED_DATA_DIR,
    RANDOM_SEED,
)
from src.features.build_features import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    engineer_features,
)
from src.models.baseline import HistoricalMedianRegressor
from src.models.evaluate import (
    compute_regression_metrics,
    compute_stratified_breakdown,
    plot_model_evaluations,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def create_chronological_split(
    df: pd.DataFrame,
    train_ratio: float = 0.75,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split traversals strictly chronologically by entry timestamp to prevent time-travel bias."""
    df_sorted = df.sort_values("t_entry").reset_index(drop=True)
    n_total = len(df_sorted)
    n_train = int(n_total * train_ratio)

    df_train = df_sorted.iloc[:n_train].copy()
    df_test = df_sorted.iloc[n_train:].copy()

    # Verify no test traversal starts before the train cutoff
    train_max_entry = df_train["t_entry"].max()
    test_min_entry = df_test["t_entry"].min()
    assert test_min_entry >= train_max_entry, "Chronological split ordering violation!"

    return df_train, df_test


def build_preprocessing_pipeline() -> ColumnTransformer:
    """Construct scikit-learn preprocessor with one-hot encoding and median-imputed scaling."""
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="unknown")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, NUMERIC_FEATURES),
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    return preprocessor


def train_and_benchmark_models(
    features_csv_path: Path = PROCESSED_DATA_DIR / "features.csv",
    output_dir: Path = OUTPUTS_DIR,
) -> Dict[str, Any]:
    """Train baseline, Random Forest, and Gradient Boosting models, evaluate, and log to MLflow."""
    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    if not features_csv_path.exists():
        raise FileNotFoundError(f"Features file not found at {features_csv_path}")

    df_all = pd.read_csv(features_csv_path)
    logger.info(f"Loaded {len(df_all)} traversal feature records.")

    # Chronological Split (75% past train, 25% future test)
    df_train, df_test = create_chronological_split(df_all, train_ratio=0.75)
    logger.info(f"Chronological split: Train = {len(df_train)} samples, Test = {len(df_test)} samples")

    X_train = df_train[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_train = df_train[TARGET_COLUMN].to_numpy()

    X_test = df_test[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_test = df_test[TARGET_COLUMN].to_numpy()

    # Configure MLflow Experiment
    try:
        mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
    except Exception as e:
        logger.warning(f"Could not set MLflow experiment: {e}")

    # Model Definitions
    models: Dict[str, Pipeline | Any] = {
        "Historical-Median Baseline": HistoricalMedianRegressor(segment_col="segment_id"),
        "Random Forest Regressor": Pipeline([
            ("preprocessor", build_preprocessing_pipeline()),
            ("regressor", RandomForestRegressor(
                n_estimators=100,
                max_depth=8,
                min_samples_split=4,
                min_samples_leaf=2,
                random_state=RANDOM_SEED,
                n_jobs=-1,
            )),
        ]),
        "Gradient Boosting Regressor": Pipeline([
            ("preprocessor", build_preprocessing_pipeline()),
            ("regressor", GradientBoostingRegressor(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                random_state=RANDOM_SEED,
            )),
        ]),
    }

    results: Dict[str, Dict[str, Any]] = {}
    summary_rows = []

    for model_name, pipeline in models.items():
        logger.info(f"\n--- Training {model_name} ---")

        with mlflow.start_run(run_name=model_name):
            # 1. Fit Model
            pipeline.fit(X_train, y_train)

            # 2. Predict on Train and Test
            train_preds = pipeline.predict(X_train)
            test_preds = pipeline.predict(X_test)

            train_metrics = compute_regression_metrics(y_train, train_preds)
            test_metrics = compute_regression_metrics(y_test, test_preds)

            logger.info(
                f"[{model_name}] Test MAE: {test_metrics['mae_minutes']:.2f} min | "
                f"Test RMSE: {test_metrics['rmse_minutes']:.2f} min | "
                f"Test R²: {test_metrics['r2_score']:.3f}"
            )

            # 3. Log to MLflow
            mlflow.log_param("model_name", model_name)
            mlflow.log_param("train_samples", len(df_train))
            mlflow.log_param("test_samples", len(df_test))
            mlflow.log_param("split_strategy", "chronological_75_25")
            mlflow.log_param("random_seed", RANDOM_SEED)

            for k, v in test_metrics.items():
                mlflow.log_metric(f"test_{k}", v)
            for k, v in train_metrics.items():
                mlflow.log_metric(f"train_{k}", v)

            # Save model binary
            sanitized_name = model_name.lower().replace(" ", "_").replace("-", "_")
            model_file = models_dir / f"{sanitized_name}.joblib"
            joblib.dump(pipeline, model_file)
            mlflow.log_artifact(str(model_file))

            results[model_name] = {
                "pipeline": pipeline,
                "y_true": y_test,
                "y_pred": test_preds,
                "metrics": test_metrics,
                "train_metrics": train_metrics,
                "model_path": model_file,
            }

            summary_rows.append({
                "Model": model_name,
                "Test MAE (min)": test_metrics["mae_minutes"],
                "Test RMSE (min)": test_metrics["rmse_minutes"],
                "Test MAPE (%)": test_metrics["mape_percent"],
                "Test R²": test_metrics["r2_score"],
                "Train MAE (min)": train_metrics["mae_minutes"],
                "Train RMSE (min)": train_metrics["rmse_minutes"],
            })

    # Summary table
    df_summary = pd.DataFrame(summary_rows).sort_values("Test MAE (min)")
    summary_path = output_dir / "model_comparison.csv"
    df_summary.to_csv(summary_path, index=False)
    logger.info("\n=== Model Benchmark Summary ===")
    print(df_summary.to_string(index=False))

    # Generate and save diagnostic figures
    saved_plots = plot_model_evaluations(results, output_dir=output_dir)
    logger.info(f"Saved evaluation plots: {list(saved_plots.keys())}")

    # Stratified Error Breakdown for the Best Performing Model
    best_model_name = df_summary.iloc[0]["Model"]
    best_test_preds = results[best_model_name]["y_pred"]
    df_eval = df_test.copy()
    df_eval["y_true"] = y_test
    df_eval["y_pred"] = best_test_preds

    breakdown_segment = compute_stratified_breakdown(df_eval, group_col="segment_id")
    breakdown_direction = compute_stratified_breakdown(df_eval, group_col="direction")
    breakdown_rush = compute_stratified_breakdown(df_eval, group_col="rush_hour_cat")

    breakdown_path = output_dir / "best_model_error_breakdown.csv"
    with open(breakdown_path, "w") as f:
        f.write("# Error Breakdown by Segment\n")
        breakdown_segment.to_csv(f, index=False)
        f.write("\n# Error Breakdown by Direction\n")
        breakdown_direction.to_csv(f, index=False)
        f.write("\n# Error Breakdown by Rush Hour Category\n")
        breakdown_rush.to_csv(f, index=False)

    logger.info(f"Best Model Selected: {best_model_name}")

    # Save best model to designated artifact path
    best_pipeline = results[best_model_name]["pipeline"]
    best_model_dest = models_dir / "best_model.joblib"
    joblib.dump(best_pipeline, best_model_dest)

    # Register best model in MLflow Registry
    try:
        with mlflow.start_run(run_name=f"SelectedBest-{best_model_name}"):
            mlflow.log_params({
                "selected_best_model": best_model_name,
                "selection_criterion": "lowest_test_mae",
                "test_mae": results[best_model_name]["metrics"]["mae_minutes"],
            })
            mlflow.sklearn.log_model(
                sk_model=best_pipeline,
                artifact_path="model",
                registered_model_name=MLFLOW_REGISTERED_MODEL_NAME,
            )
            logger.info(f"Successfully registered '{best_model_name}' as '{MLFLOW_REGISTERED_MODEL_NAME}' in MLflow.")
    except Exception as e:
        logger.warning(f"MLflow model registration note: {e}")

    return {
        "summary": df_summary,
        "best_model": best_model_name,
        "results": results,
    }


if __name__ == "__main__":
    train_and_benchmark_models()
