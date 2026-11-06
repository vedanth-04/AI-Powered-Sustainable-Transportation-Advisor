"""Unit tests for model baselines, training pipelines, and evaluation metrics."""

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, engineer_features
from src.features.segment_config import SEGMENT_ORR_EASTBOUND
from src.models.baseline import HistoricalMedianRegressor
from src.models.evaluate import compute_regression_metrics
from src.models.train import (
    build_preprocessing_pipeline,
    create_chronological_split,
    load_training_features,
)
from src.models.train_cold_start import split_by_date


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


def test_cold_start_split_excludes_labels_finishing_at_cutoffs():
    validation_start = date(2019, 7, 5)
    test_start = date(2019, 7, 8)
    validation_cutoff = datetime.fromisoformat("2019-07-05T00:00:00+05:30").timestamp()
    test_cutoff = datetime.fromisoformat("2019-07-08T00:00:00+05:30").timestamp()
    exits = np.array([
        validation_cutoff - 120, validation_cutoff - 60, validation_cutoff,
        validation_cutoff + 120, validation_cutoff + 180, test_cutoff + 30,
        test_cutoff + 60, test_cutoff + 120,
    ])
    traversals = pd.DataFrame({
        "t_entry": exits - 60,
        "t_exit": exits,
        "travel_time_minutes": 1.0,
    })

    training, validation, test = split_by_date(traversals, validation_start, test_start)

    assert training.index.tolist() == [0, 1]
    assert validation.index.tolist() == [3, 4]
    assert test.index.tolist() == [6, 7]


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


def test_route_90_cold_start_training_serving_parity(tmp_path):
    segment = SEGMENT_ORR_EASTBOUND
    entry_at = datetime.fromisoformat("2019-07-01T17:10:00+05:30")
    request = {
        "segment_id": segment.segment_id,
        "direction": segment.direction,
        "segment_length_km": segment.length_km,
        "route_id": "90",
        "t_entry": entry_at.timestamp(),
    }
    traversals = pd.DataFrame([
        {**request, "t_entry": request["t_entry"] - 600, "t_exit": request["t_entry"] - 120,
         "entry_hour": 17, "entry_minute": 0, "travel_time_minutes": 8.0},
        {**request, "t_exit": request["t_entry"] + 300, "entry_hour": 17,
         "entry_minute": 10, "travel_time_minutes": 5.0},
    ])
    assert engineer_features(traversals).loc[1, "hist_completed_count"] == 1

    feature_path = tmp_path / "features.csv"
    engineer_features(traversals, use_observed_history=False).to_csv(feature_path, index=False)
    feature_columns = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    training = load_training_features(feature_path)[feature_columns]
    serving = engineer_features(pd.DataFrame([request]), use_observed_history=False)[feature_columns]

    assert len(feature_columns) == 12
    assert training.loc[1, "route_id"] == serving.loc[0, "route_id"] == "90"
    assert serving.loc[0, "minute_of_day"] == 17 * 60 + 10
    assert serving.loc[0, "hist_completed_count"] == 0
    fallback_minutes = segment.length_km / 22 * 60
    assert serving.loc[0, "hist_segment_median_tt"] == pytest.approx(fallback_minutes)
    assert serving.loc[0, "hist_recent_60m_mean_tt"] == pytest.approx(fallback_minutes)
    training_trip = training.iloc[[1]].reset_index(drop=True)
    pd.testing.assert_frame_equal(training_trip, serving, check_dtype=True)

    preprocessor = build_preprocessing_pipeline().fit(training)
    np.testing.assert_allclose(
        preprocessor.transform(training_trip), preprocessor.transform(serving), atol=1e-12
    )


def test_permutation_importance_detects_predictive_signal(tmp_path):
    """A fitted signal beats independent noise on unseen synthetic samples."""
    from sklearn.tree import DecisionTreeRegressor
    from src.models.importance import save_feature_importance

    rng = np.random.default_rng(42)
    train = pd.DataFrame({"signal": rng.normal(size=300), "noise": rng.normal(size=300)})
    test = pd.DataFrame({"signal": rng.normal(size=150), "noise": rng.normal(size=150)})
    model = DecisionTreeRegressor(max_depth=4, random_state=42)
    model.fit(train, 10 * train["signal"])
    csv_path, png_path = save_feature_importance(
        model, test, 10 * test["signal"], tmp_path, "synthetic", n_repeats=5,
    )
    result = pd.read_csv(csv_path).set_index("feature")
    assert result.loc["signal", "mae_increase_mean_minutes"] > 5
    assert result.loc["signal", "mae_increase_mean_minutes"] > result.loc["noise", "mae_increase_mean_minutes"]
    assert (result["evaluation_samples"] == 150).all()
    assert png_path.stat().st_size > 0
