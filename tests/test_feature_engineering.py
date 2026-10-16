"""Unit tests for feature engineering, cyclical encoding, and leakage prevention safeguards."""

import numpy as np
import pandas as pd
import pytest

from src.features.build_features import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    compute_causal_historical_statistics,
    compute_rush_hour_category,
    engineer_features,
)


def test_rush_hour_categories():
    """Verify operational period categorization for Delhi transit."""
    assert compute_rush_hour_category(8) == "MORNING_RUSH"
    assert compute_rush_hour_category(10) == "MORNING_RUSH"
    assert compute_rush_hour_category(14) == "MIDDAY"
    assert compute_rush_hour_category(18) == "EVENING_RUSH"
    assert compute_rush_hour_category(20) == "EVENING_RUSH"
    assert compute_rush_hour_category(22) == "OFF_PEAK"
    assert compute_rush_hour_category(4) == "OFF_PEAK"


def test_cyclical_time_encoding_bounds():
    """Sine and cosine cyclical encodings must be strictly bounded in [-1.0, 1.0]."""
    df = pd.DataFrame({
        "t_entry": [1561939200, 1561960800, 1561982400],  # 00:00, 06:00, 12:00
        "t_exit": [1561939600, 1561961200, 1561982800],
        "travel_time_minutes": [6.67, 6.67, 6.67],
        "segment_id": ["SEG1", "SEG1", "SEG1"],
        "direction": ["EASTBOUND", "EASTBOUND", "EASTBOUND"],
        "route_id": ["90", "90", "90"],
        "segment_length_km": [2.63, 2.63, 2.63],
        "entry_hour": [5, 11, 17],
        "entry_minute": [30, 0, 30],
        "avg_speed_kmh": [25.0, 25.0, 25.0],
    })
    res = engineer_features(df)

    assert "sin_time" in res.columns
    assert "cos_time" in res.columns
    assert (res["sin_time"] >= -1.0).all() and (res["sin_time"] <= 1.0).all()
    assert (res["cos_time"] >= -1.0).all() and (res["cos_time"] <= 1.0).all()


def test_no_future_data_leakage():
    """Modifying future observations must have ZERO impact on past historical features."""
    base_data = [
        # Bus 1: enters 1000, exits 1400 (travel time 6.67 min)
        {"t_entry": 1000.0, "t_exit": 1400.0, "travel_time_minutes": 6.67, "segment_id": "SEG1", "segment_length_km": 2.5},
        # Bus 2: enters 1500, exits 1900 (travel time 6.67 min)
        {"t_entry": 1500.0, "t_exit": 1900.0, "travel_time_minutes": 6.67, "segment_id": "SEG1", "segment_length_km": 2.5},
        # Bus 3: enters 2000, exits 2400 (travel time 6.67 min)
        {"t_entry": 2000.0, "t_exit": 2400.0, "travel_time_minutes": 6.67, "segment_id": "SEG1", "segment_length_km": 2.5},
    ]
    df1 = pd.DataFrame(base_data)
    res1 = compute_causal_historical_statistics(df1)

    # Now create df2 where Bus 3 has an extreme delay (travel time 25 min)
    mutated_data = [
        {"t_entry": 1000.0, "t_exit": 1400.0, "travel_time_minutes": 6.67, "segment_id": "SEG1", "segment_length_km": 2.5},
        {"t_entry": 1500.0, "t_exit": 1900.0, "travel_time_minutes": 6.67, "segment_id": "SEG1", "segment_length_km": 2.5},
        {"t_entry": 2000.0, "t_exit": 3500.0, "travel_time_minutes": 25.0, "segment_id": "SEG1", "segment_length_km": 2.5},  # future extreme change
    ]
    df2 = pd.DataFrame(mutated_data)
    res2 = compute_causal_historical_statistics(df2)

    # Bus 1 and Bus 2 historical features must be EXACTLY IDENTICAL
    assert res1.loc[0, "hist_segment_median_tt"] == pytest.approx(res2.loc[0, "hist_segment_median_tt"])
    assert res1.loc[1, "hist_segment_median_tt"] == pytest.approx(res2.loc[1, "hist_segment_median_tt"])
    assert res1.loc[1, "hist_recent_60m_mean_tt"] == pytest.approx(res2.loc[1, "hist_recent_60m_mean_tt"])


def test_no_concurrent_overlap_leakage():
    """If Bus A enters at 1000 and exits at 1500, Bus B entering at 1200 must NOT see Bus A."""
    data = [
        # Bus A: enters 1000, exits 1500 (still inside when Bus B enters!)
        {"t_entry": 1000.0, "t_exit": 1500.0, "travel_time_minutes": 8.33, "segment_id": "SEG1", "segment_length_km": 2.5},
        # Bus B: enters 1200 (Bus A has NOT exited yet)
        {"t_entry": 1200.0, "t_exit": 1600.0, "travel_time_minutes": 6.67, "segment_id": "SEG1", "segment_length_km": 2.5},
        # Bus C: enters 1600 (both Bus A and Bus B have completed)
        {"t_entry": 1600.0, "t_exit": 2000.0, "travel_time_minutes": 6.67, "segment_id": "SEG1", "segment_length_km": 2.5},
    ]
    df = pd.DataFrame(data)
    res = compute_causal_historical_statistics(df)

    # Bus B enters at 1200 while Bus A exits at 1500.
    # Therefore, Bus B must have 0 completed traversals in memory!
    assert res.loc[1, "hist_completed_count"] == 0

    # Bus C enters at 1600 after both A and B completed, so it sees 2 completed traversals.
    assert res.loc[2, "hist_completed_count"] == 2
    assert res.loc[2, "hist_segment_median_tt"] == pytest.approx(np.median([8.33, 6.67]), abs=1e-3)


def test_feature_columns_schema_complete():
    """Verify that all required modeling columns are generated without missing values."""
    traversals = pd.DataFrame({
        "segment_id": ["ORR_CHIRAG_TO_NEHRU_PLACE_EB", "ORR_CHIRAG_TO_NEHRU_PLACE_EB"],
        "direction": ["EASTBOUND", "EASTBOUND"],
        "route_id": ["90", "90"],
        "vehicle_id": ["BUS1", "BUS2"],
        "t_entry": [1561940000.0, 1561940500.0],
        "t_exit": [1561940400.0, 1561940900.0],
        "travel_time_minutes": [6.67, 6.67],
        "segment_length_km": [2.63, 2.63],
        "avg_speed_kmh": [23.6, 23.6],
        "entry_hour": [6, 6],
        "entry_minute": [15, 23],
    })

    features = engineer_features(traversals)

    for col in CATEGORICAL_FEATURES + NUMERIC_FEATURES + [TARGET_COLUMN]:
        assert col in features.columns, f"Missing expected feature column: {col}"
        assert features[col].isnull().sum() == 0, f"Null values found in feature column: {col}"


def test_target_derived_speed_is_excluded():
    """Current-journey answers and stale aliases cannot change model inputs."""
    df = pd.DataFrame({
        "t_entry": [1000.0], "t_exit": [1600.0],
        "travel_time_minutes": [10.0], "segment_id": ["SEG1"],
        "segment_length_km": [3.0], "direction": ["EASTBOUND"],
        "route_id": ["90"], "avg_speed_kmh": [18.0],
        "approach_speed_kmh": [18.0],
    })
    before = engineer_features(df)
    changed = df.assign(t_exit=2200.0, travel_time_minutes=20.0,
                        avg_speed_kmh=9.0, approach_speed_kmh=9.0)
    after = engineer_features(changed)
    inputs = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    assert "approach_speed_kmh" not in inputs
    assert "avg_speed_kmh" not in inputs
    assert "approach_speed_kmh" not in before.columns
    pd.testing.assert_frame_equal(before[inputs], after[inputs])
