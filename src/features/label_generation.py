"""Segment travel-time label generation and gate crossing extraction module.

Detects vehicle crossings across defined spatial road segment boundaries,
interpolates sub-second crossing timestamps, enforces trajectory continuity,
and constructs ground-truth travel-time regression targets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.config import (
    MAX_CROSSING_PING_GAP_SEC,
    MAX_TRAVEL_TIME_MINUTES,
    MAX_WITHIN_SEGMENT_GAP_SEC,
    MIN_TRAVEL_TIME_MINUTES,
)
from src.features.segment_config import PRIMARY_SEGMENT, RoadSegment

logger = logging.getLogger(__name__)

# India Standard Time offset (UTC + 05:30 = 19,800 seconds)
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))


@dataclass
class LabelGenerationSummary:
    """Summary of gate crossing detections and traversal validation outcomes."""

    segment_id: str = ""
    candidate_subtrips_evaluated: int = 0
    entry_crossings_detected: int = 0
    exit_crossings_detected: int = 0
    valid_traversals_generated: int = 0
    rejected_no_exit: int = 0
    rejected_internal_gap: int = 0
    rejected_duration_bounds: int = 0
    rejected_speed_bounds: int = 0
    unique_buses_with_traversals: int = 0


def extract_gate_crossing(
    subtrip_df: pd.DataFrame,
    gate,
    direction_sign: int,
    after_timestamp: Optional[float] = None,
    max_ping_gap: float = MAX_CROSSING_PING_GAP_SEC,
) -> Optional[Tuple[float, int, int]]:
    """Detect when a vehicle trajectory crosses a spatial gate.

    Parameters
    ----------
    subtrip_df : DataFrame for a single continuous vehicle journey sorted by timestamp.
    gate : SpatialGate boundary line.
    direction_sign : +1 for eastbound/northbound, -1 for westbound/southbound.
    after_timestamp : If provided, only search for crossings occurring strictly after this time.
    max_ping_gap : Maximum allowable time gap between the straddling pings.

    Returns
    -------
    Optional tuple of (interpolated_epoch_timestamp, prev_row_index, curr_row_index).
    """
    n_pts = len(subtrip_df)
    if n_pts < 2:
        return None

    lats = subtrip_df["lat"].to_numpy()
    lngs = subtrip_df["lng"].to_numpy()
    timestamps = subtrip_df["timestamp"].to_numpy()

    for i in range(n_pts - 1):
        t1, t2 = timestamps[i], timestamps[i + 1]

        if after_timestamp is not None and t1 < after_timestamp:
            continue

        ping_dt = t2 - t1
        if ping_dt <= 0 or ping_dt > max_ping_gap:
            continue

        lat1, lng1 = lats[i], lngs[i]
        lat2, lng2 = lats[i + 1], lngs[i + 1]

        has_crossed, frac = gate.straddled_by(lat1, lng1, lat2, lng2, direction_sign)
        if has_crossed:
            t_cross = float(t1) + float(frac) * float(ping_dt)
            return t_cross, i, i + 1

    return None


def extract_segment_traversals(
    cleaned_df: pd.DataFrame,
    segment: RoadSegment = PRIMARY_SEGMENT,
    max_within_gap_sec: float = MAX_WITHIN_SEGMENT_GAP_SEC,
    min_duration_min: float = MIN_TRAVEL_TIME_MINUTES,
    max_duration_min: float = MAX_TRAVEL_TIME_MINUTES,
    summary: Optional[LabelGenerationSummary] = None,
) -> pd.DataFrame:
    """Extract all valid segment traversals and calculate ground-truth travel times.

    Parameters
    ----------
    cleaned_df : Cleaned, deduplicated DataFrame with 'subtrip_id' and 'timestamp'.
    segment : Physical RoadSegment defining entry/exit gates and bounds.
    max_within_gap_sec : Max ping gap tolerated during the traversal itself.
    min_duration_min : Minimum valid travel time in minutes.
    max_duration_min : Maximum valid travel time in minutes.
    summary : Optional summary accumulator for audit reporting.

    Returns
    -------
    pd.DataFrame
        Table of valid traversals with target 'travel_time_minutes' and provenance fields.
    """
    stats = summary if summary is not None else LabelGenerationSummary(segment_id=segment.segment_id)
    stats.segment_id = segment.segment_id

    traversals: List[Dict] = []

    # Filter to observations in the segment's broad spatial envelope
    lat_min, lat_max = segment.bounding_lat_range
    lng_min, lng_max = segment.bounding_lng_range

    in_envelope = (
        cleaned_df["lat"].between(lat_min, lat_max)
        & cleaned_df["lng"].between(lng_min, lng_max)
    )
    df_corridor = cleaned_df[in_envelope].copy()

    # Filter to primary routes if specified and available
    if segment.primary_routes and "route_id" in df_corridor.columns:
        route_mask = df_corridor["route_id"].isin(segment.primary_routes)
        df_corridor = df_corridor[route_mask].copy()

    if df_corridor.empty:
        return pd.DataFrame()

    # Process each continuous subtrip
    for (vid, st_id), group in df_corridor.groupby(["vehicle_id", "subtrip_id"]):
        stats.candidate_subtrips_evaluated += 1
        group = group.sort_values("timestamp").reset_index(drop=True)
        if len(group) < 3:
            continue

        route_id = group["route_id"].iloc[0] if "route_id" in group.columns else "unknown"

        # 1. Search for entry gate crossing
        entry_result = extract_gate_crossing(
            group,
            gate=segment.entry_gate,
            direction_sign=segment.direction_sign,
            after_timestamp=None,
        )
        if entry_result is None:
            continue

        t_entry, entry_p1_idx, _ = entry_result
        stats.entry_crossings_detected += 1

        # 2. Search for exit gate crossing AFTER entry
        exit_result = extract_gate_crossing(
            group,
            gate=segment.exit_gate,
            direction_sign=segment.direction_sign,
            after_timestamp=t_entry,
        )
        if exit_result is None:
            stats.rejected_no_exit += 1
            continue

        t_exit, _, exit_p2_idx = exit_result
        stats.exit_crossings_detected += 1

        if t_exit <= t_entry:
            continue

        # 3. Trajectory continuity within traversal
        # Sub-slice points between entry and exit
        in_traversal_pts = group.iloc[entry_p1_idx : exit_p2_idx + 1]
        traversal_dts = in_traversal_pts["timestamp"].diff().dropna()

        if (traversal_dts > max_within_gap_sec).any():
            stats.rejected_internal_gap += 1
            continue

        # 4. Target travel time calculation
        travel_time_sec = t_exit - t_entry
        travel_time_min = travel_time_sec / 60.0

        if not (min_duration_min <= travel_time_min <= max_duration_min):
            stats.rejected_duration_bounds += 1
            continue

        # 5. Kinematic average speed check
        hours = travel_time_min / 60.0
        avg_speed_kmh = segment.length_km / hours if hours > 0 else 0.0
        if avg_speed_kmh > 70.0:  # Infeasible urban bus average speed
            stats.rejected_speed_bounds += 1
            continue

        # Temporal metadata in UTC and IST
        dt_entry_utc = datetime.fromtimestamp(t_entry, tz=timezone.utc)
        dt_entry_ist = dt_entry_utc.astimezone(IST_OFFSET)
        dt_exit_ist = datetime.fromtimestamp(t_exit, tz=timezone.utc).astimezone(IST_OFFSET)

        traversals.append({
            "segment_id": segment.segment_id,
            "corridor_name": segment.corridor_name,
            "direction": segment.direction,
            "vehicle_id": str(vid),
            "route_id": str(route_id),
            "t_entry": float(t_entry),
            "t_exit": float(t_exit),
            "travel_time_minutes": float(travel_time_min),
            "segment_length_km": float(segment.length_km),
            "avg_speed_kmh": float(avg_speed_kmh),
            "num_pings": int(len(in_traversal_pts)),
            "entry_time_ist": dt_entry_ist.strftime("%H:%M:%S"),
            "exit_time_ist": dt_exit_ist.strftime("%H:%M:%S"),
            "entry_hour": int(dt_entry_ist.hour),
            "entry_minute": int(dt_entry_ist.minute),
            "date": dt_entry_ist.strftime("%Y-%m-%d"),
        })
        stats.valid_traversals_generated += 1

    df_traversals = pd.DataFrame(traversals)
    if not df_traversals.empty:
        stats.unique_buses_with_traversals = int(df_traversals["vehicle_id"].nunique())
        df_traversals = df_traversals.sort_values("t_entry").reset_index(drop=True)

    return df_traversals
