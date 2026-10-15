"""Data loader module for SQLite bus telemetry archives."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd

from src.config import DEFAULT_RAW_DB

logger = logging.getLogger(__name__)


def get_readonly_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Open a SQLite connection in read-only mode using a URI."""
    path = Path(db_path) if db_path is not None else DEFAULT_RAW_DB
    if not path.exists():
        raise FileNotFoundError(f"Database file not found at: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def load_corridor_observations(
    routes: Optional[List[str]] = None,
    lat_range: Optional[tuple[float, float]] = None,
    lng_range: Optional[tuple[float, float]] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Load observation records filtered by routes and/or bounding box.

    Parameters
    ----------
    routes : Optional list of route string IDs (e.g. ['90', '83']).
    lat_range : Optional (min_lat, max_lat) tuple.
    lng_range : Optional (min_lng, max_lng) tuple.
    db_path : Optional path to raw SQLite database file.

    Returns
    -------
    pd.DataFrame
        Loaded observations.
    """
    where_clauses = ["lat IS NOT NULL", "lng IS NOT NULL", "timestamp IS NOT NULL"]

    if routes:
        float_routes = [f"{float(r):.1f}" for r in routes if r.replace(".", "", 1).isdigit()]
        if float_routes:
            formatted_routes = ", ".join(float_routes)
            where_clauses.append(f"route_id IN ({formatted_routes})")

    if lat_range:
        where_clauses.append(f"CAST(lat AS REAL) BETWEEN {lat_range[0]} AND {lat_range[1]}")

    if lng_range:
        where_clauses.append(f"CAST(lng AS REAL) BETWEEN {lng_range[0]} AND {lng_range[1]}")

    query = f"""
        SELECT 
            vehicle_id,
            route_id,
            trip_id,
            CAST(timestamp AS INTEGER) as timestamp,
            CAST(lat AS REAL) as lat,
            CAST(lng AS REAL) as lng,
            speed,
            date,
            time
        FROM vehicle_feed
        WHERE {" AND ".join(where_clauses)}
        ORDER BY vehicle_id, timestamp ASC;
    """

    with get_readonly_connection(db_path) as conn:
        df = pd.read_sql_query(query, conn)

    return df
