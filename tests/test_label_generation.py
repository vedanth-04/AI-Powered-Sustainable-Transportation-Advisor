"""Unit tests for segment crossing detection, interpolation, and label generation."""

import pandas as pd
import pytest

from src.features.label_generation import (
    LabelGenerationSummary,
    extract_gate_crossing,
    extract_segment_traversals,
)
from src.features.segment_config import ORR_GATE_WEST, SEGMENT_ORR_EASTBOUND


def test_gate_crossing_interpolation_precision():
    """Verify linear interpolation yields exact sub-second crossing timestamp."""
    # Gate West is at lng = 77.2180
    # Ping 1 at t=1000, lng=77.2170 (0.0010 before gate)
    # Ping 2 at t=1010, lng=77.2190 (0.0010 after gate)
    # Crossing should occur at exactly t=1005.0 (fraction 0.5)
    data = [
        {"lat": 28.542, "lng": 77.2170, "timestamp": 1000},
        {"lat": 28.542, "lng": 77.2190, "timestamp": 1010},
    ]
    df = pd.DataFrame(data)
    result = extract_gate_crossing(df, gate=ORR_GATE_WEST, direction_sign=1)

    assert result is not None
    t_cross, p1_idx, p2_idx = result
    assert t_cross == pytest.approx(1005.0, abs=1e-4)
    assert p1_idx == 0
    assert p2_idx == 1


def test_extract_segment_traversals_valid_journey():
    """Synthetic trajectory that cleanly crosses entry and exit gates must generate 1 valid label."""
    # Segment: 77.2180 -> 77.2450 (length ~2.63 km)
    # Bus moves from 77.215 to 77.250 over 360 seconds (6 minutes)
    timestamps = [1000, 1010, 1100, 1200, 1360, 1370]
    lngs = [77.2160, 77.2190, 77.2250, 77.2350, 77.2440, 77.2480]
    lats = [28.542] * len(timestamps)

    data = [
        {
            "vehicle_id": "TEST_BUS",
            "route_id": "90",
            "subtrip_id": 1,
            "timestamp": ts,
            "lat": lat,
            "lng": lng,
        }
        for ts, lat, lng in zip(timestamps, lats, lngs)
    ]
    df = pd.DataFrame(data)

    summary = LabelGenerationSummary()
    traversals = extract_segment_traversals(df, segment=SEGMENT_ORR_EASTBOUND, summary=summary)

    assert len(traversals) == 1
    row = traversals.iloc[0]
    assert row["vehicle_id"] == "TEST_BUS"
    assert row["route_id"] == "90"
    assert 5.0 <= row["travel_time_minutes"] <= 7.0
    assert 20.0 <= row["avg_speed_kmh"] <= 35.0
    assert summary.valid_traversals_generated == 1


def test_extract_segment_traversals_gap_rejection():
    """Traversal containing an internal gap > 180s must be rejected to prevent dwell/outage bias."""
    # Bus crosses entry, but then has a 300s gap before exiting
    timestamps = [1000, 1010, 1320, 1330]  # 310s gap between idx 1 and 2
    lngs = [77.2160, 77.2190, 77.2440, 77.2480]
    lats = [28.542] * len(timestamps)

    data = [
        {
            "vehicle_id": "TEST_BUS",
            "route_id": "90",
            "subtrip_id": 1,
            "timestamp": ts,
            "lat": lat,
            "lng": lng,
        }
        for ts, lat, lng in zip(timestamps, lats, lngs)
    ]
    df = pd.DataFrame(data)

    summary = LabelGenerationSummary()
    traversals = extract_segment_traversals(
        df, segment=SEGMENT_ORR_EASTBOUND, max_within_gap_sec=180.0, summary=summary
    )

    assert traversals.empty
    assert summary.rejected_internal_gap == 1


def test_extract_segment_traversals_duration_out_of_bounds():
    """Unrealistic travel time (< 1 min or > 45 min) must be rejected."""
    # Superfast crossing: 10 seconds (implied speed ~950 km/h)
    timestamps = [1000, 1005, 1010, 1015]
    lngs = [77.2160, 77.2200, 77.2440, 77.2480]
    lats = [28.542] * len(timestamps)

    data = [
        {
            "vehicle_id": "TEST_BUS",
            "route_id": "90",
            "subtrip_id": 1,
            "timestamp": ts,
            "lat": lat,
            "lng": lng,
        }
        for ts, lat, lng in zip(timestamps, lats, lngs)
    ]
    df = pd.DataFrame(data)

    summary = LabelGenerationSummary()
    traversals = extract_segment_traversals(
        df, segment=SEGMENT_ORR_EASTBOUND, min_duration_min=1.0, summary=summary
    )

    assert traversals.empty
    assert (summary.rejected_duration_bounds + summary.rejected_speed_bounds) >= 1
