"""Unit tests for trajectory cleaning, deduplication, GPS jump filtering, and gap segmentation."""

import pandas as pd
import pytest

from src.data.cleaner import CleaningAuditLog, clean_trajectory_data


def test_clean_trajectory_empty():
    """Empty dataframe must return empty dataframe without error."""
    df = pd.DataFrame(columns=["vehicle_id", "timestamp", "lat", "lng", "speed"])
    res = clean_trajectory_data(df)
    assert res.empty


def test_clean_trajectory_deduplication():
    """Duplicate (vehicle_id, timestamp) rows must be removed, preserving the first."""
    data = [
        {"vehicle_id": "BUS1", "timestamp": 1000, "lat": 28.542, "lng": 77.2150, "speed": 1.0},
        {"vehicle_id": "BUS1", "timestamp": 1000, "lat": 28.542, "lng": 77.2150, "speed": 1.0},  # duplicate
        {"vehicle_id": "BUS1", "timestamp": 1010, "lat": 28.542, "lng": 77.2155, "speed": 2.0},  # ~49m in 10s = ~17.6 km/h
    ]
    df = pd.DataFrame(data)
    audit = CleaningAuditLog()
    res = clean_trajectory_data(df, log_audit=audit)

    assert len(res) == 2
    assert audit.duplicate_rows_dropped == 1


def test_clean_trajectory_out_of_bounds():
    """Coordinates far outside Delhi bounding box must be dropped."""
    data = [
        {"vehicle_id": "BUS1", "timestamp": 1000, "lat": 28.542, "lng": 77.215, "speed": 1.0},
        {"vehicle_id": "BUS1", "timestamp": 1010, "lat": 12.971, "lng": 77.594, "speed": 1.0},  # Bangalore coordinates
    ]
    df = pd.DataFrame(data)
    audit = CleaningAuditLog()
    res = clean_trajectory_data(df, log_audit=audit)

    assert len(res) == 1
    assert audit.out_of_bounds_coords == 1


def test_clean_trajectory_gps_jump_filtered():
    """Implausible teleportation jump (> 80 km/h) over a short interval must be filtered."""
    # 0.05 degrees longitude at lat 28.5 is approx 4.87 km
    # 4.87 km in 10 seconds is over 1750 km/h
    data = [
        {"vehicle_id": "BUS1", "timestamp": 1000, "lat": 28.542, "lng": 77.210, "speed": 1.0},
        {"vehicle_id": "BUS1", "timestamp": 1010, "lat": 28.542, "lng": 77.260, "speed": 1.0},  # teleportation jump
        {"vehicle_id": "BUS1", "timestamp": 1020, "lat": 28.542, "lng": 77.212, "speed": 1.0},
    ]
    df = pd.DataFrame(data)
    audit = CleaningAuditLog()
    res = clean_trajectory_data(df, max_speed_kmh=80.0, log_audit=audit)

    assert audit.gps_jumps_rejected >= 1


def test_clean_trajectory_gap_segmentation():
    """A time gap > 300s must increment subtrip_id into distinct continuous segments."""
    data = [
        {"vehicle_id": "BUS1", "timestamp": 1000, "lat": 28.542, "lng": 77.210, "speed": 1.0},
        {"vehicle_id": "BUS1", "timestamp": 1010, "lat": 28.542, "lng": 77.212, "speed": 1.0},
        # 600 second gap (layover)
        {"vehicle_id": "BUS1", "timestamp": 1610, "lat": 28.542, "lng": 77.214, "speed": 1.0},
        {"vehicle_id": "BUS1", "timestamp": 1620, "lat": 28.542, "lng": 77.216, "speed": 1.0},
    ]
    df = pd.DataFrame(data)
    res = clean_trajectory_data(df, max_gap_sec=300.0)

    assert "subtrip_id" in res.columns
    subtrips = res["subtrip_id"].unique()
    assert len(subtrips) == 2
