"""Data validation and promotion checks that every retrained candidate must pass."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.segment_config import REGISTERED_SEGMENTS

IST_SECONDS = 19800


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def validate_training_data(traversals: pd.DataFrame, policy: dict) -> dict:
    """Refuse to train on data that could not have come from a healthy feed."""
    rules = policy["data_validation"]
    checks = []
    missing_columns = [c for c in rules["required_columns"] if c not in traversals.columns]
    checks.append(_check("required_columns", not missing_columns,
                         "all present" if not missing_columns else f"missing {missing_columns}"))
    if missing_columns:
        return {"passed": False, "rows": len(traversals), "checks": checks}
    frame = traversals[rules["required_columns"]]
    nulls = int(frame.isna().any(axis=1).sum())
    checks.append(_check("no_missing_values", nulls == 0, f"{nulls} rows with missing values"))
    checks.append(_check("minimum_rows", len(frame) >= rules["min_rows"], f"{len(frame)} rows (minimum {rules['min_rows']})"))
    duration = frame["travel_time_minutes"].astype(float)
    in_bounds = duration.between(rules["min_travel_time_minutes"], rules["max_travel_time_minutes"])
    checks.append(_check("duration_bounds", in_bounds.all(),
                         f"{int((~in_bounds).sum())} durations outside {rules['min_travel_time_minutes']}-{rules['max_travel_time_minutes']} min"))
    implied = (frame["t_exit"].astype(float) - frame["t_entry"].astype(float)) / 60.0
    consistent = (implied - duration).abs() <= rules["duration_tolerance_minutes"]
    checks.append(_check("timestamps_match_label", consistent.all(),
                         f"{int((~consistent).sum())} rows where exit minus entry differs from the label"))
    hours = pd.to_datetime(frame["t_entry"].astype(float) + IST_SECONDS, unit="s", utc=True).dt.hour
    low, high = rules["service_hours"]
    inside = hours.between(low, high)
    checks.append(_check("service_hours", inside.all(),
                         f"{int((~inside).sum())} entries outside {low:02d}:00-{high:02d}:59 IST (timezone fault?)"))
    unknown = [(s, r) for s, r in zip(frame["segment_id"].astype(str), frame["route_id"].astype(str))
               if s not in REGISTERED_SEGMENTS or r not in REGISTERED_SEGMENTS[s].primary_routes]
    checks.append(_check("registered_segment_routes", not unknown,
                         f"{len(unknown)} rows with an unregistered segment/route" + (f", e.g. {unknown[0]}" if unknown else "")))
    duplicates = int(frame.duplicated(["segment_id", "route_id", "t_entry"]).sum())
    checks.append(_check("no_duplicate_traversals", duplicates == 0, f"{duplicates} duplicates"))
    return {"passed": all(item["passed"] for item in checks), "rows": len(frame), "checks": checks}


def promotion_checks(*, data_validation: dict, candidate: dict, champion: dict, baseline: dict,
                     segment_table: pd.DataFrame, schema_matches: bool, reload_max_diff: float,
                     predictions_valid: bool, policy: dict) -> dict:
    """Candidate vs champion on the same holdout; each rule is reported separately."""
    rules = policy["promotion"]
    required_mae = champion["mae_minutes"] * (1 - rules["min_relative_mae_improvement"])
    improvement = 1 - candidate["mae_minutes"] / champion["mae_minutes"]
    worst = segment_table.assign(change=segment_table["candidate_mae"] / segment_table["champion_mae"] - 1)
    worst_row = worst.loc[worst["change"].idxmax()]
    checks = [
        _check("data_validation", data_validation["passed"],
               "training data passed every validation rule" if data_validation["passed"] else
               "failed: " + ", ".join(c["name"] for c in data_validation["checks"] if not c["passed"])),
        _check("valid_predictions", predictions_valid, "finite and positive on the whole holdout"),
        _check("beats_champion", candidate["mae_minutes"] <= required_mae,
               f"MAE {candidate['mae_minutes']:.3f} vs champion {champion['mae_minutes']:.3f} "
               f"({improvement:+.1%}; required at least {rules['min_relative_mae_improvement']:.0%} better)"),
        _check("beats_median_baseline", (not rules["require_beats_median_baseline"])
               or candidate["mae_minutes"] < baseline["mae_minutes"],
               f"MAE {candidate['mae_minutes']:.3f} vs retrained median {baseline['mae_minutes']:.3f}"),
        _check("no_segment_regression", worst_row["change"] <= rules["max_segment_mae_regression"],
               f"worst segment {worst_row['segment_id']}: {worst_row['change']:+.1%} "
               f"(limit +{rules['max_segment_mae_regression']:.0%})"),
        _check("same_feature_schema", (not rules["require_same_feature_schema"]) or schema_matches,
               "matches the API's cold_start_v1 schema" if schema_matches else "differs from the serving schema"),
        _check("reload_parity", (not rules["require_reload_parity"]) or reload_max_diff <= rules["reload_tolerance_minutes"],
               f"max difference after save/reload {reload_max_diff:.2e} min"),
    ]
    return {"passed": all(item["passed"] for item in checks), "checks": checks,
            "relative_mae_improvement": float(improvement)}


def segment_comparison(holdout: pd.DataFrame, candidate_pred: np.ndarray, champion_pred: np.ndarray) -> pd.DataFrame:
    frame = holdout.assign(candidate_error=np.abs(candidate_pred - holdout["travel_time_minutes"].to_numpy()),
                           champion_error=np.abs(champion_pred - holdout["travel_time_minutes"].to_numpy()))
    table = frame.groupby("segment_id").agg(rows=("candidate_error", "size"), candidate_mae=("candidate_error", "mean"),
                                            champion_mae=("champion_error", "mean")).reset_index()
    return table
