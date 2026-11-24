"""Request data-quality checks that run before drift statistics are trusted."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.features.segment_config import REGISTERED_SEGMENTS

IST_SECONDS = 19800


@dataclass(frozen=True)
class QualityReference:
    """What the approved model saw during training."""

    routes_by_segment: dict[str, frozenset[str]]
    min_hour: int
    max_hour: int

    @classmethod
    def from_training(cls, training: pd.DataFrame) -> "QualityReference":
        hours = (pd.to_datetime(training["t_entry"] + IST_SECONDS, unit="s", utc=True).dt.hour)
        routes = {
            str(segment): frozenset(group["route_id"].astype(str))
            for segment, group in training.groupby("segment_id")
        }
        return cls(routes, int(hours.min()), int(hours.max()))


def ist_hour(epoch_seconds: pd.Series) -> pd.Series:
    return pd.to_datetime(epoch_seconds + IST_SECONDS, unit="s", utc=True).dt.hour


def request_flags(requests: pd.DataFrame, reference: QualityReference, *, skew_minutes: float) -> pd.DataFrame:
    """One boolean column per data-quality problem, for every request."""
    required = ["segment_id", "route_id", "entry_ts_sent", "received_at"]
    missing = requests[required].isna().any(axis=1)
    segment = requests["segment_id"].astype(str)
    route = requests["route_id"].astype(str)
    unknown_segment = ~segment.isin(list(REGISTERED_SEGMENTS))
    unseen_route = np.array([
        r not in reference.routes_by_segment.get(s, frozenset()) for s, r in zip(segment, route)
    ])
    hours = ist_hour(requests["entry_ts_sent"].astype(float))
    outside_hours = (hours < reference.min_hour) | (hours > reference.max_hour)
    # In the replay a request describes a bus entering the segment now, so its stated
    # entry time should match the moment the server received it.
    skew = (requests["entry_ts_sent"].astype(float) - requests["received_at"].astype(float)).abs() > skew_minutes * 60
    return pd.DataFrame({
        "missing_field": missing.to_numpy(),
        "unknown_segment": unknown_segment.to_numpy(),
        "unseen_route": unseen_route & ~unknown_segment.to_numpy(),
        "outside_service_hours": outside_hours.to_numpy(),
        "timestamp_skew": skew.to_numpy(),
    }, index=requests.index)


def summarize_quality(flags: pd.DataFrame, *, alert_rate: float) -> dict:
    """Rates per check; any problem is a warning and a rate above `alert_rate` is an alert."""
    rates = {name: float(flags[name].mean()) if len(flags) else 0.0 for name in flags.columns}
    any_rate = float(flags.any(axis=1).mean()) if len(flags) else 0.0
    status = "ALERT" if any_rate > alert_rate else "WARN" if any_rate > 0 else "OK"
    return {"rates": rates, "any_problem_rate": any_rate, "status": status}
