"""Controlled drift injection on top of the real held-out replay stream.

Every scenario starts from real traversals. Injections are labelled on each event,
so injected and genuine behaviour can always be told apart in the evidence.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from src.features.build_features import TARGET_COLUMN

EVENT_COLUMNS = [
    "event_id", "received_at", "segment_id", "route_id", "direction", "segment_length_km",
    "entry_ts_sent", "actual_minutes", "label_at", "injected", "injection", "source_row",
]


def base_events(stream: pd.DataFrame) -> pd.DataFrame:
    """Turn held-out traversals into prediction requests with delayed labels."""
    ordered = stream.sort_values("t_entry", kind="stable")
    events = pd.DataFrame({
        "received_at": ordered["t_entry"].astype(float).to_numpy(),
        "segment_id": ordered["segment_id"].astype(str).to_numpy(),
        "route_id": ordered["route_id"].astype(str).to_numpy(),
        "direction": ordered["direction"].astype(str).to_numpy(),
        "segment_length_km": ordered["segment_length_km"].astype(float).to_numpy(),
        "entry_ts_sent": ordered["t_entry"].astype(float).to_numpy(),
        "actual_minutes": ordered[TARGET_COLUMN].astype(float).to_numpy(),
        "injected": False,
        "injection": "",
        "source_row": ordered.index.to_numpy(),
    })
    return _finalize(events)


def _finalize(events: pd.DataFrame) -> pd.DataFrame:
    events = events.sort_values(["received_at", "source_row"], kind="stable").reset_index(drop=True)
    events["label_at"] = events["received_at"] + events["actual_minutes"] * 60.0
    events["event_id"] = [f"evt-{position:04d}" for position in range(len(events))]
    return events[EVENT_COLUMNS]


def _onset(params: dict) -> float:
    return datetime.fromisoformat(params["onset_ist"]).timestamp()


def natural(events: pd.DataFrame, params: dict, rng: np.random.Generator) -> pd.DataFrame:
    return events.copy()


def covariate_shift(events: pd.DataFrame, params: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Resample post-onset traffic toward one segment and the evening, keeping real labels."""
    onset = _onset(params)
    before, after = events[events["received_at"] < onset], events[events["received_at"] >= onset]
    if after.empty:
        return events.copy()
    hours = pd.to_datetime(after["received_at"] + 19800, unit="s", utc=True).dt.hour.to_numpy()
    weights = np.where(hours >= params["evening_start_hour"], params["evening_weight"], 1.0)
    weights = weights * after["segment_id"].map(params.get("segment_weights", {})).fillna(1.0).to_numpy()
    chosen = rng.choice(len(after), size=len(after), replace=True, p=weights / weights.sum())
    shifted = after.iloc[chosen].copy()
    shifted["injected"] = True
    shifted["injection"] = "demand_mix_resampled"
    return _finalize(pd.concat([before, shifted], ignore_index=True))


def concept_drift(events: pd.DataFrame, params: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Slow one segment down after onset; the request features do not change."""
    out = events.copy()
    affected = (out["received_at"] >= _onset(params)) & (out["segment_id"] == params["segment_id"])
    out.loc[affected, "actual_minutes"] *= float(params["duration_multiplier"])
    out.loc[affected, "injected"] = True
    out.loc[affected, "injection"] = f"riding_time_x{params['duration_multiplier']}"
    return _finalize(out)


def data_quality(events: pd.DataFrame, params: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Corrupt part of the post-onset requests the way a broken upstream feed would."""
    out = events.copy()
    candidates = np.flatnonzero((out["received_at"] >= _onset(params)).to_numpy())
    draws = rng.random(len(candidates))
    tz_rows = candidates[draws < params["timezone_fault_fraction"]]
    route_rows = candidates[(draws >= params["timezone_fault_fraction"])
                            & (draws < params["timezone_fault_fraction"] + params["unknown_route_fraction"])]
    out.loc[out.index[tz_rows], "entry_ts_sent"] += float(params["timezone_shift_minutes"]) * 60.0
    out.loc[out.index[tz_rows], "injection"] = "timezone_shift"
    out.loc[out.index[route_rows], "route_id"] = str(params["unknown_route_id"])
    out.loc[out.index[route_rows], "injection"] = "unknown_route"
    out.loc[out.index[np.concatenate([tz_rows, route_rows])], "injected"] = True
    return _finalize(out)


SCENARIOS = {
    "natural": natural,
    "covariate_shift": covariate_shift,
    "concept_drift": concept_drift,
    "data_quality": data_quality,
}


def apply_scenario(events: pd.DataFrame, name: str, params: dict, seed: int) -> pd.DataFrame:
    if name not in SCENARIOS:
        raise KeyError(f"Unknown scenario {name}; choose one of {sorted(SCENARIOS)}.")
    return SCENARIOS[name](events, params, np.random.default_rng(seed))
