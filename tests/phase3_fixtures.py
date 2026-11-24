"""Synthetic traversals shaped like the Phase 2 input, for Phase 3 tests (no real data needed)."""

from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.label_generation import IST_OFFSET
from src.features.segment_config import list_segments
from src.monitoring.replay import DEFAULT_POLICY

DAYS = ("2019-07-01", "2019-07-02", "2019-07-03", "2019-07-05", "2019-07-08")
BASE_MINUTES = {"ORR_CHIRAG_TO_NEHRU_PLACE_EB": 6.5, "ORR_NEHRU_PLACE_TO_CHIRAG_WB": 6.0,
                "MB_SAKET_TO_KHANPUR_EB": 10.0, "MB_KHANPUR_TO_SAKET_WB": 12.0}


def synthetic_traversals(seed: int = 7, slow_last_day: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for day in DAYS:
        for segment in list_segments():
            for hour in range(6, 23):
                for _ in range(1 + int(rng.random() < 0.5)):
                    start = datetime.fromisoformat(f"{day}T{hour:02d}:{int(rng.integers(0, 60)):02d}:00").replace(tzinfo=IST_OFFSET)
                    rush = 1.35 if hour in (8, 9, 10, 17, 18, 19, 20) else 1.0
                    minutes = BASE_MINUTES[segment.segment_id] * rush * rng.uniform(0.85, 1.15)
                    if day == DAYS[-1]:
                        minutes *= slow_last_day
                    t_entry = start.timestamp() + float(rng.uniform(0, 60))
                    rows.append({"segment_id": segment.segment_id, "corridor_name": segment.corridor_name,
                                 "direction": segment.direction, "vehicle_id": f"BUS{len(rows)}",
                                 "route_id": segment.primary_routes[0], "t_entry": t_entry,
                                 "t_exit": t_entry + minutes * 60, "travel_time_minutes": minutes,
                                 "segment_length_km": segment.length_km, "date": day})
    return pd.DataFrame(rows)


def fast_policy(tmp_path) -> Path:
    """The real monitoring policy with fewer resamples so tests stay quick."""
    policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
    policy["thresholds"]["bootstrap_iterations"] = 200
    policy["performance_detector"]["calibration_iterations"] = 300
    path = tmp_path / "monitoring_policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    return path
