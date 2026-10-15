"""Leakage-safe feature engineering pipeline for urban bus segment travel-time prediction.

Defines the prediction moment (t_entry) and extracts temporal, spatial, kinematic,
and causal historical statistics without future-data or target leakage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

logger = logging.getLogger(__name__)

# Feature Column Definitions
CATEGORICAL_FEATURES = ["segment_id", "direction", "route_id", "rush_hour_cat"]
NUMERIC_FEATURES = [
    "segment_length_km",
    "entry_hour",
    "minute_of_day",
    "sin_time",
    "cos_time",
    "approach_speed_kmh",
    "hist_segment_median_tt",
    "hist_recent_60m_mean_tt",
    "hist_completed_count",
]
TARGET_COLUMN = "travel_time_minutes"


def compute_rush_hour_category(hour: int) -> str:
    """Classify Delhi transit operational rush-hour periods."""
    if 8 <= hour < 11:
        return "MORNING_RUSH"
    elif 17 <= hour < 21:
        return "EVENING_RUSH"
    elif 11 <= hour < 17:
        return "MIDDAY"
    else:
        return "OFF_PEAK"


def compute_causal_historical_statistics(
    df: pd.DataFrame,
    window_sec: float = 3600.0,  # 60-minute rolling traffic window
    nominal_fallback_speed_kmh: float = 22.0,
) -> pd.DataFrame:
    """Compute rolling historical travel-time statistics with strictly causal conditioning.

    PREDICTION MOMENT GUARANTEE:
    For any traversal i with entry timestamp t_entry, an earlier traversal j is ONLY
    eligible for inclusion in historical aggregates if it has fully completed BEFORE
    bus i enters the segment:
        t_exit(j) <= t_entry(i)

    This strictly eliminates future-data leakage and ensures historical features are
    reproducibly computable in real-time production.
    """
    n = len(df)
    hist_median = np.zeros(n, dtype=np.float64)
    hist_recent = np.zeros(n, dtype=np.float64)
    hist_count = np.zeros(n, dtype=np.int32)

    # Ensure chronological order by entry time
    sorted_indices = np.argsort(df["t_entry"].to_numpy())
    df_sorted = df.iloc[sorted_indices].reset_index(drop=True)

    t_entries = df_sorted["t_entry"].to_numpy()
    t_exits = df_sorted["t_exit"].to_numpy()
    targets = df_sorted[TARGET_COLUMN].to_numpy()
    segment_ids = df_sorted["segment_id"].to_numpy()
    segment_lengths = df_sorted["segment_length_km"].to_numpy()

    # Pre-calculate nominal fallback durations for cold-start cases
    # nominal_time_min = (length_km / 22 km/h) * 60 min
    fallback_durations = (segment_lengths / nominal_fallback_speed_kmh) * 60.0

    for i in range(n):
        curr_t_entry = t_entries[i]
        curr_seg = segment_ids[i]
        curr_fallback = fallback_durations[i]

        # Find eligible completed traversals on the same segment
        # Condition: t_exit <= curr_t_entry AND segment_id == curr_seg
        completed_mask = (t_exits[:i] <= curr_t_entry) & (segment_ids[:i] == curr_seg)

        if not np.any(completed_mask):
            # Cold-start: no completed prior traversals on this segment yet
            hist_median[i] = curr_fallback
            hist_recent[i] = curr_fallback
            hist_count[i] = 0
        else:
            eligible_targets = targets[:i][completed_mask]
            hist_median[i] = float(np.median(eligible_targets))
            hist_count[i] = int(len(eligible_targets))

            # Recent 60-minute window condition:
            # (curr_t_entry - window_sec) <= t_exit <= curr_t_entry
            recent_mask = (t_exits[:i] >= curr_t_entry - window_sec) & completed_mask
            if np.any(recent_mask):
                hist_recent[i] = float(np.mean(targets[:i][recent_mask]))
            else:
                hist_recent[i] = hist_median[i]

    # Map back to original row indexing
    reverse_indices = np.empty_like(sorted_indices)
    reverse_indices[sorted_indices] = np.arange(n)

    result_df = df.copy()
    result_df["hist_segment_median_tt"] = hist_median[reverse_indices]
    result_df["hist_recent_60m_mean_tt"] = hist_recent[reverse_indices]
    result_df["hist_completed_count"] = hist_count[reverse_indices]

    return result_df


class TransitFeatureEngineer(BaseEstimator, TransformerMixin):
    """Scikit-learn compatible transformer that constructs leakage-free transit features."""

    def __init__(self, window_sec: float = 3600.0, nominal_fallback_speed_kmh: float = 22.0):
        self.window_sec = window_sec
        self.nominal_fallback_speed_kmh = nominal_fallback_speed_kmh

    def fit(self, X: pd.DataFrame, y=None):
        """Fit transformer (records schema and validates input columns)."""
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Transform raw traversal DataFrame into model-ready features."""
        df = X.copy()

        # 1. Temporal & Cyclical Features
        if "entry_hour" not in df.columns:
            # Derive from t_entry (epoch to IST)
            ist_times = pd.to_datetime(df["t_entry"] + 19800, unit="s", utc=True)
            df["entry_hour"] = ist_times.dt.hour
            df["entry_minute"] = ist_times.dt.minute

        df["minute_of_day"] = df["entry_hour"] * 60.0 + df["entry_minute"].astype(float)
        # 1440 minutes in a day
        radians = (2.0 * np.pi * df["minute_of_day"]) / 1440.0
        df["sin_time"] = np.sin(radians)
        df["cos_time"] = np.cos(radians)
        df["rush_hour_cat"] = df["entry_hour"].apply(compute_rush_hour_category)

        # 2. Approach Kinematics
        # If avg_speed_kmh is present, derive approach proxy or use historical bounds
        if "avg_speed_kmh" in df.columns:
            # Clip between 5 and 60 km/h
            df["approach_speed_kmh"] = df["avg_speed_kmh"].clip(lower=5.0, upper=60.0)
        else:
            df["approach_speed_kmh"] = self.nominal_fallback_speed_kmh

        # 3. Categorical normalizations
        df["route_id"] = df["route_id"].astype(str)
        df["direction"] = df["direction"].astype(str)
        df["segment_id"] = df["segment_id"].astype(str)

        # 4. Causal historical statistics (leakage-safe)
        if TARGET_COLUMN in df.columns and "t_exit" in df.columns:
            df = compute_causal_historical_statistics(
                df,
                window_sec=self.window_sec,
                nominal_fallback_speed_kmh=self.nominal_fallback_speed_kmh,
            )
        else:
            # Inference mode without targets
            df["hist_segment_median_tt"] = (df["segment_length_km"] / self.nominal_fallback_speed_kmh) * 60.0
            df["hist_recent_60m_mean_tt"] = df["hist_segment_median_tt"]
            df["hist_completed_count"] = 0

        return df


def engineer_features(traversals_df: pd.DataFrame) -> pd.DataFrame:
    """Convenience functional wrapper around TransitFeatureEngineer."""
    engineer = TransitFeatureEngineer()
    return engineer.transform(traversals_df)
