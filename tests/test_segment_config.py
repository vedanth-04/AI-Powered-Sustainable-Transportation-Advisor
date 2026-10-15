"""Unit tests for spatial gate and road segment configuration."""

import math
import pytest

from src.features.segment_config import (
    ORR_GATE_WEST,
    ORR_GATE_EAST,
    SEGMENT_ORR_EASTBOUND,
    SEGMENT_ORR_WESTBOUND,
    haversine_distance_km,
    get_segment,
    list_segments,
    SpatialGate,
)


def test_haversine_zero_distance():
    """Distance from a point to itself must be exactly 0."""
    dist = haversine_distance_km(28.542, 77.218, 28.542, 77.218)
    assert dist == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_meridian_distance():
    """1 degree latitude along a meridian is approximately 111.19 km."""
    dist = haversine_distance_km(28.0, 77.0, 29.0, 77.0)
    assert dist == pytest.approx(111.19, abs=0.5)


def test_spatial_gate_clean_eastbound_crossing():
    """Consecutive pings crossing longitude gate from west to east."""
    gate = ORR_GATE_WEST  # reference_coord = 77.2180
    prev_lat, prev_lng = 28.542, 77.2170
    curr_lat, curr_lng = 28.542, 77.2190

    crossed, frac = gate.straddled_by(prev_lat, prev_lng, curr_lat, curr_lng, direction_sign=1)
    assert crossed is True
    assert frac == pytest.approx(0.5, abs=1e-4)


def test_spatial_gate_clean_westbound_crossing():
    """Consecutive pings crossing longitude gate from east to west."""
    gate = ORR_GATE_WEST  # reference_coord = 77.2180
    prev_lat, prev_lng = 28.542, 77.2190
    curr_lat, curr_lng = 28.542, 77.2170

    crossed, frac = gate.straddled_by(prev_lat, prev_lng, curr_lat, curr_lng, direction_sign=-1)
    assert crossed is True
    assert frac == pytest.approx(0.5, abs=1e-4)


def test_spatial_gate_wrong_direction_rejected():
    """Eastbound movement against westbound gate expectation must be rejected."""
    gate = ORR_GATE_WEST
    prev_lat, prev_lng = 28.542, 77.2170
    curr_lat, curr_lng = 28.542, 77.2190

    # Gate expects westbound (-1), but movement is eastbound (+1)
    crossed, frac = gate.straddled_by(prev_lat, prev_lng, curr_lat, curr_lng, direction_sign=-1)
    assert crossed is False
    assert frac == 0.0


def test_spatial_gate_out_of_bounds_latitude_rejected():
    """Pings at wrong latitude (e.g. North Delhi) must not trigger South Delhi gate."""
    gate = ORR_GATE_WEST  # lat bounds [28.535, 28.550]
    prev_lat, prev_lng = 28.700, 77.2170
    curr_lat, curr_lng = 28.700, 77.2190

    crossed, frac = gate.straddled_by(prev_lat, prev_lng, curr_lat, curr_lng, direction_sign=1)
    assert crossed is False
    assert frac == 0.0


def test_registered_segments_catalog():
    """Verify registry lookup and error handling."""
    segments = list_segments()
    assert len(segments) >= 4

    orr_eb = get_segment("ORR_CHIRAG_TO_NEHRU_PLACE_EB")
    assert orr_eb.direction == "EASTBOUND"
    assert "90" in orr_eb.primary_routes
    assert 2.0 <= orr_eb.length_km <= 3.5

    with pytest.raises(KeyError):
        get_segment("NON_EXISTENT_SEGMENT")
