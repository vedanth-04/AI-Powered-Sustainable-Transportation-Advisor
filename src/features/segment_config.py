"""Physical road segment and boundary gate definitions for travel-time modeling.

Defines real, empirically verified geographic corridor segments and spatial gate
lines in Delhi for bus travel-time label construction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on the earth in km."""
    radius_earth_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.asin(math.sqrt(max(0.0, min(1.0, a))))
    return radius_earth_km * c


@dataclass(frozen=True)
class SpatialGate:
    """Represents a spatial boundary line segment (gate) across a roadway.

    Vehicles crossing this gate trigger entry or exit timestamps.
    """

    gate_id: str
    description: str
    lat_min: float
    lat_max: float
    lng_min: float
    lng_max: float
    # Orientation: 'LONGITUDE' if the gate is a north-south line at constant longitude,
    # 'LATITUDE' if the gate is an east-west line at constant latitude.
    orientation: str = "LONGITUDE"
    reference_coord: float = 0.0  # The longitude (or latitude) value of the crossing plane

    def straddled_by(
        self,
        prev_lat: float,
        prev_lng: float,
        curr_lat: float,
        curr_lng: float,
        direction_sign: int,
    ) -> Tuple[bool, float]:
        """Check if consecutive pings cross the gate line in the designated direction.

        Parameters
        ----------
        prev_lat, prev_lng : Coordinates of prior observation
        curr_lat, curr_lng : Coordinates of current observation
        direction_sign : +1 if increasing coord (e.g. Eastbound / Northbound),
                         -1 if decreasing coord (e.g. Westbound / Southbound).

        Returns
        -------
        Tuple of (has_crossed, interpolation_fraction)
        """
        if self.orientation == "LONGITUDE":
            # Check bounding latitude envelope
            if not (self.lat_min <= max(prev_lat, curr_lat) and min(prev_lat, curr_lat) <= self.lat_max):
                return False, 0.0

            ref = self.reference_coord
            if direction_sign > 0:
                # Eastbound: prev_lng <= ref < curr_lng
                if prev_lng <= ref < curr_lng:
                    frac = (ref - prev_lng) / (curr_lng - prev_lng) if curr_lng != prev_lng else 0.0
                    return True, frac
            else:
                # Westbound: prev_lng >= ref > curr_lng
                if prev_lng >= ref > curr_lng:
                    frac = (prev_lng - ref) / (prev_lng - curr_lng) if prev_lng != curr_lng else 0.0
                    return True, frac
        elif self.orientation == "LATITUDE":
            # Check bounding longitude envelope
            if not (self.lng_min <= max(prev_lng, curr_lng) and min(prev_lng, curr_lng) <= self.lng_max):
                return False, 0.0

            ref = self.reference_coord
            if direction_sign > 0:
                # Northbound: prev_lat <= ref < curr_lat
                if prev_lat <= ref < curr_lat:
                    frac = (ref - prev_lat) / (curr_lat - prev_lat) if curr_lat != prev_lat else 0.0
                    return True, frac
            else:
                # Southbound: prev_lat >= ref > curr_lat
                if prev_lat >= ref > curr_lat:
                    frac = (prev_lat - ref) / (prev_lat - curr_lat) if prev_lat != curr_lat else 0.0
                    return True, frac

        return False, 0.0


@dataclass(frozen=True)
class RoadSegment:
    """Defines a physical road segment bounded by an entry and exit gate."""

    segment_id: str
    corridor_name: str
    direction: str  # e.g., 'EASTBOUND', 'WESTBOUND'
    direction_sign: int  # +1 or -1
    entry_gate: SpatialGate
    exit_gate: SpatialGate
    length_km: float
    bounding_lat_range: Tuple[float, float]
    bounding_lng_range: Tuple[float, float]
    primary_routes: List[str] = field(default_factory=list)
    description: str = ""


# =============================================================================
# VERIFIED DELHI CORRIDOR 1: Outer Ring Road (Chirag Delhi <-> Nehru Place / GK)
# =============================================================================
# West Gate: Chirag Delhi Flyover western approach / Khel Gaon Marg junction
ORR_GATE_WEST = SpatialGate(
    gate_id="ORR_GATE_WEST",
    description="Chirag Delhi Flyover West Approach (77.2180 E, Lat 28.535-28.550)",
    lat_min=28.535,
    lat_max=28.550,
    lng_min=77.2175,
    lng_max=77.2185,
    orientation="LONGITUDE",
    reference_coord=77.2180,
)

# East Gate: Greater Kailash-II / Savitri Flyover / Nehru Place west approach
ORR_GATE_EAST = SpatialGate(
    gate_id="ORR_GATE_EAST",
    description="Greater Kailash / Nehru Place Flyover West Approach (77.2450 E, Lat 28.535-28.550)",
    lat_min=28.535,
    lat_max=28.550,
    lng_min=77.2445,
    lng_max=77.2455,
    orientation="LONGITUDE",
    reference_coord=77.2450,
)

# Primary Segment 1: Outer Ring Road Eastbound (Route 90, Route 163, Route 164)
SEGMENT_ORR_EASTBOUND = RoadSegment(
    segment_id="ORR_CHIRAG_TO_NEHRU_PLACE_EB",
    corridor_name="Outer Ring Road (South Delhi)",
    direction="EASTBOUND",
    direction_sign=1,
    entry_gate=ORR_GATE_WEST,
    exit_gate=ORR_GATE_EAST,
    length_km=haversine_distance_km(28.542, 77.2180, 28.542, 77.2450),  # ~2.63 km
    bounding_lat_range=(28.535, 28.550),
    bounding_lng_range=(77.210, 77.255),
    primary_routes=["90", "163", "164"],
    description="Outer Ring Road eastbound grade-separated arterial from Chirag Delhi to Nehru Place / Greater Kailash.",
)

# Secondary Segment 1: Outer Ring Road Westbound (Route 83, Route 163, Route 164)
SEGMENT_ORR_WESTBOUND = RoadSegment(
    segment_id="ORR_NEHRU_PLACE_TO_CHIRAG_WB",
    corridor_name="Outer Ring Road (South Delhi)",
    direction="WESTBOUND",
    direction_sign=-1,
    entry_gate=ORR_GATE_EAST,
    exit_gate=ORR_GATE_WEST,
    length_km=haversine_distance_km(28.542, 77.2450, 28.542, 77.2180),  # ~2.63 km
    bounding_lat_range=(28.535, 28.550),
    bounding_lng_range=(77.210, 77.255),
    primary_routes=["83", "163", "164"],
    description="Outer Ring Road westbound grade-separated arterial from Nehru Place to Chirag Delhi.",
)


# =============================================================================
# VERIFIED DELHI CORRIDOR 2: Mehrauli-Badarpur Road (Saket Metro <-> Khanpur)
# =============================================================================
MB_GATE_WEST = SpatialGate(
    gate_id="MB_GATE_WEST",
    description="Saket Metro / Said-ul-Azaib Western Boundary (77.2000 E, Lat 28.505-28.525)",
    lat_min=28.505,
    lat_max=28.525,
    lng_min=77.1995,
    lng_max=77.2005,
    orientation="LONGITUDE",
    reference_coord=77.2000,
)

MB_GATE_EAST = SpatialGate(
    gate_id="MB_GATE_EAST",
    description="Khanpur / Hamdard Nagar Eastern Boundary (77.2300 E, Lat 28.505-28.525)",
    lat_min=28.505,
    lat_max=28.525,
    lng_min=77.2295,
    lng_max=77.2305,
    orientation="LONGITUDE",
    reference_coord=77.2300,
)

SEGMENT_MB_EASTBOUND = RoadSegment(
    segment_id="MB_SAKET_TO_KHANPUR_EB",
    corridor_name="Mehrauli-Badarpur Road (SH-2)",
    direction="EASTBOUND",
    direction_sign=1,
    entry_gate=MB_GATE_WEST,
    exit_gate=MB_GATE_EAST,
    length_km=haversine_distance_km(28.515, 77.2000, 28.515, 77.2300),  # ~2.93 km
    bounding_lat_range=(28.505, 28.525),
    bounding_lng_range=(77.195, 77.235),
    primary_routes=["398", "376"],
    description="Mehrauli-Badarpur Road eastbound surface arterial from Saket Metro to Khanpur intersection.",
)

SEGMENT_MB_WESTBOUND = RoadSegment(
    segment_id="MB_KHANPUR_TO_SAKET_WB",
    corridor_name="Mehrauli-Badarpur Road (SH-2)",
    direction="WESTBOUND",
    direction_sign=-1,
    entry_gate=MB_GATE_EAST,
    exit_gate=MB_GATE_WEST,
    length_km=haversine_distance_km(28.515, 77.2300, 28.515, 77.2000),  # ~2.93 km
    bounding_lat_range=(28.505, 28.525),
    bounding_lng_range=(77.195, 77.235),
    primary_routes=["399", "376"],
    description="Mehrauli-Badarpur Road westbound surface arterial from Khanpur intersection to Saket Metro.",
)


# Registry of verified segments
REGISTERED_SEGMENTS: Dict[str, RoadSegment] = {
    SEGMENT_ORR_EASTBOUND.segment_id: SEGMENT_ORR_EASTBOUND,
    SEGMENT_ORR_WESTBOUND.segment_id: SEGMENT_ORR_WESTBOUND,
    SEGMENT_MB_EASTBOUND.segment_id: SEGMENT_MB_EASTBOUND,
    SEGMENT_MB_WESTBOUND.segment_id: SEGMENT_MB_WESTBOUND,
}

# Primary recommended segment for single-corridor modeling
PRIMARY_SEGMENT = SEGMENT_ORR_EASTBOUND


def get_segment(segment_id: str) -> RoadSegment:
    """Retrieve registered segment by ID or raise KeyError with available options."""
    if segment_id not in REGISTERED_SEGMENTS:
        available = ", ".join(REGISTERED_SEGMENTS.keys())
        raise KeyError(f"Unknown segment '{segment_id}'. Available segments: {available}")
    return REGISTERED_SEGMENTS[segment_id]


def list_segments() -> List[RoadSegment]:
    """Return all registered segments."""
    return list(REGISTERED_SEGMENTS.values())
