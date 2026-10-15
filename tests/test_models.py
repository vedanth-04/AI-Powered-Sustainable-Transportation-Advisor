"""Unit tests for model baselines, training pipelines, and evaluation metrics."""

import numpy as np
import pandas as pd
import pytest

from src.models.baseline import HistoricalMedianRegressor
from src.models.evaluate import compute_regression_metrics
from src.models.train import build_preprocessing_pipeline, create_chronological_split


def test_baseline_regressor_fit_and_fallback():
    """Verify historical median fits per-segment medians and uses global median for unseen segments."""
    X = pd.DataFrame({"segment_id": ["SEG_A", "SEG_A", "SEG_A", "SEG_B", "SEG_B"]})
    y = np.array([5.0, 6.0, 7.0, 10.0, 12.0])  # Median SEG_A = 6.0, Median SEG_B = 11.0, Global = 7.0

    model = HistoricalMedianRegressor(segment_col="segment_id")
    model.fit(X, y)

    assert model.segment_medians_["SEG_A"] == pytest.approx(6.0)
    assert model.segment_medians_["SEG_B"] == pytest.approx(11.0)
    assert model.global_median_ == pytest.approx(7.0)

    # Test predictions including unseen segment
    X_test = pd.DataFrame({"segment_id": ["SEG_A", "SEG_B", "UNSEEN_SEG"]})
    preds = model.predict(X_test)
    assert preds[0] == pytest.approx(6.0)
    assert preds[1] == pytest.approx(11.0)
    assert preds[2] == pytest.approx(7.0)  # global fallback


def test_chronological_split_ordering():
    """Verify that test split contains strictly future observations relative to train split."""
    df = pd.DataFrame({
        "t_entry": [100.0, 200.0, 300.0, 400.0],
        "travel_time_minutes": [5.0, 6.0, 7.0, 8.0],
    })
    df_train, df_test = create_chronological_split(df, train_ratio=0.75)

    assert len(df_train) == 3
    assert len(df_test) == 1
    assert df_test["t_entry"].min() >= df_train["t_entry"].max()


def test_compute_regression_metrics_perfect_prediction():
    """Perfect predictions must yield exactly 0.0 MAE and RMSE, and 1.0 R²."""
    y_true = np.array([5.0, 6.0, 7.0, 8.0])
    metrics = compute_regression_metrics(y_true, y_true)

    assert metrics["mae_minutes"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["rmse_minutes"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["r2_score"] == pytest.approx(1.0, abs=1e-6)


def test_preprocessing_pipeline_transforms_features():
    """Verify preprocessing pipeline transforms tabular mixed features without error."""
    preprocessor = build_preprocessing_pipeline()
    X = pd.DataFrame({
        "segment_id": ["SEG_A", "SEG_B"],
        "direction": ["EASTBOUND", "WESTBOUND"],
        "route_id": ["90", "83"],
        "rush_hour_cat": ["MORNING_RUSH", "MIDDAY"],
        "segment_length_km": [2.63, 2.63],
        "entry_hour": [8, 12],
        "minute_of_day": [510.0, 750.0],
        "sin_time": [0.5, -0.5],
        "cos_time": [0.8, -0.8],
        "approach_speed_kmh": [25.0, 30.0],
        "hist_segment_median_tt": [6.0, 6.0],
        "hist_recent_60m_mean_tt": [6.2, 5.8],
        "hist_completed_count": [5, 10],
    })
    transformed = preprocessor.fit_transform(X)
    assert transformed.shape[0] == 2
    assert transformed.shape[1] > 0
    assert not np.isnan(transformed).any()
