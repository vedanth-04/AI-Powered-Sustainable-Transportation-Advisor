"""Trajectory cleaning, validation, and segmentation module.

Provides deterministic deduplication, coordinate bounding validation,
GPS jump filtering, and trajectory gap segmentation for Delhi bus AVL records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from src.config import (
    DELHI_LAT_MAX,
    DELHI_LAT_MIN,
    DELHI_LNG_MAX,
    DELHI_LNG_MIN,
    MAX_IMPLIED_SPEED_KMH,
    MAX_TRAJECTORY_GAP_SEC,
)

logger = logging.getLogger(__name__)


def haversine_vectorized(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    """Compute haversine distances in kilometers for coordinate arrays."""
    radius_km = 6371.0
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
    )
    a_clipped = np.clip(a, 0.0, 1.0)
    return 2.0 * radius_km * np.arcsin(np.sqrt(a_clipped))


@dataclass
class CleaningAuditLog:
    """Summary of records retained and rejected during trajectory cleaning."""

    total_input_rows: int = 0
    out_of_bounds_coords: int = 0
    duplicate_rows_dropped: int = 0
    gps_jumps_rejected: int = 0
    clean_rows_retained: int = 0
    subtrips_generated: int = 0
    unique_vehicles: int = 0


def clean_trajectory_data(
    df: pd.DataFrame,
    max_speed_kmh: float = MAX_IMPLIED_SPEED_KMH,
    max_gap_sec: float = MAX_TRAJECTORY_GAP_SEC,
    log_audit: Optional[CleaningAuditLog] = None,
) -> pd.DataFrame:
    """Clean, deduplicate, filter GPS jumps, and segment trajectories across gaps.

    Parameters
    ----------
    df : Raw DataFrame containing vehicle_id, timestamp, lat, lng, speed, route_id.
    max_speed_kmh : Maximum physically plausible velocity between pings in km/h.
    max_gap_sec : Sampling gap in seconds triggering trajectory sub-segmentation.
    log_audit : Optional CleaningAuditLog instance to populate with diagnostics.

    Returns
    -------
    pd.DataFrame
        Cleaned, chronologically sorted DataFrame with 'dt', 'disp_km', 'implied_kmh',
        and 'subtrip_id' assigned per continuous journey segment.
    """
    if df.empty:
        return df.copy()

    required_cols = {"vehicle_id", "timestamp", "lat", "lng"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Input DataFrame is missing required columns: {missing}")

    audit = log_audit if log_audit is not None else CleaningAuditLog()
    audit.total_input_rows = len(df)

    clean_df = df.copy()

    # 1. Type normalization
    clean_df["lat"] = pd.to_numeric(clean_df["lat"], errors="coerce")
    clean_df["lng"] = pd.to_numeric(clean_df["lng"], errors="coerce")
    clean_df["timestamp"] = pd.to_numeric(clean_df["timestamp"], errors="coerce").astype("int64")
    if "speed" in clean_df.columns:
        clean_df["speed"] = pd.to_numeric(clean_df["speed"], errors="coerce").fillna(0.0)
    if "route_id" in clean_df.columns:
        clean_df["route_id"] = clean_df["route_id"].apply(
            lambda x: str(int(float(x))) if pd.notnull(x) and str(x).strip() != "" else "unknown"
        )

    # 2. Coordinate boundary validation
    valid_coords = (
        clean_df["lat"].between(DELHI_LAT_MIN, DELHI_LAT_MAX)
        & clean_df["lng"].between(DELHI_LNG_MIN, DELHI_LNG_MAX)
    )
    audit.out_of_bounds_coords = int((~valid_coords).sum())
    clean_df = clean_df[valid_coords].copy()

    # 3. Deterministic deduplication on (vehicle_id, timestamp)
    before_dup = len(clean_df)
    clean_df = clean_df.drop_duplicates(subset=["vehicle_id", "timestamp"], keep="first").copy()
    audit.duplicate_rows_dropped = before_dup - len(clean_df)

    # 4. Chronological sorting
    clean_df = clean_df.sort_values(["vehicle_id", "timestamp"]).reset_index(drop=True)

    # 5. Kinematic metrics & GPS jump detection
    clean_df["dt"] = clean_df.groupby("vehicle_id")["timestamp"].diff()
    clean_df["prev_lat"] = clean_df.groupby("vehicle_id")["lat"].shift(1)
    clean_df["prev_lng"] = clean_df.groupby("vehicle_id")["lng"].shift(1)

    has_prev = clean_df["prev_lat"].notnull() & (clean_df["dt"] > 0)
    clean_df["disp_km"] = 0.0
    clean_df["implied_kmh"] = 0.0

    if has_prev.any():
        displacements = haversine_vectorized(
            clean_df.loc[has_prev, "prev_lat"].to_numpy(),
            clean_df.loc[has_prev, "prev_lng"].to_numpy(),
            clean_df.loc[has_prev, "lat"].to_numpy(),
            clean_df.loc[has_prev, "lng"].to_numpy(),
        )
        clean_df.loc[has_prev, "disp_km"] = displacements
        time_hours = clean_df.loc[has_prev, "dt"] / 3600.0
        clean_df.loc[has_prev, "implied_kmh"] = clean_df.loc[has_prev, "disp_km"] / time_hours

    # Identify jumps for active consecutive pings (dt <= 60s) where implied speed is anomalous
    jump_mask = (clean_df["dt"].between(1, 60)) & (clean_df["implied_kmh"] > max_speed_kmh)
    audit.gps_jumps_rejected = int(jump_mask.sum())
    clean_df = clean_df[~jump_mask].copy()

    # Recompute dt after jump removal
    clean_df["dt"] = clean_df.groupby("vehicle_id")["timestamp"].diff()

    # 6. Trajectory gap segmentation
    # A new continuous journey starts whenever dt is null (first ping of vehicle)
    # or dt > max_gap_sec (layover / signal outage).
    gap_trigger = clean_df["dt"].isnull() | (clean_df["dt"] > max_gap_sec)
    clean_df["subtrip_id"] = gap_trigger.cumsum()

    audit.clean_rows_retained = len(clean_df)
    audit.subtrips_generated = int(clean_df["subtrip_id"].nunique())
    audit.unique_vehicles = int(clean_df["vehicle_id"].nunique())

    clean_df = clean_df.drop(columns=["prev_lat", "prev_lng"], errors="ignore")
    return clean_df
