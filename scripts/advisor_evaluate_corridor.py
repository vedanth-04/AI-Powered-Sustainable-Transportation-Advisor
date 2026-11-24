"""Does the trained bus model improve the advisor's corridor times over the timetable and historical medians?

    .\\.venv-dev\\Scripts\\python.exe -m scripts.advisor_evaluate_corridor

On the one corridor where the advisor uses the model (ORR_CHIRAG_TO_NEHRU_PLACE_EB), this compares three
estimates of the gate-to-gate riding time against the observed 8 July 2019 traversals (the Phase 3 holdout):

  timetable   what the planner uses without a model: the OTD GTFS stop_times (constant-speed estimates)
  median      the historical-median baseline trained on the same days as the model (Phase 3 gate baseline)
  model       the champion's prediction (needs no model here: predictions come from holdout_predictions.csv)

It reports MAE/RMSE/bias, and a connection proxy: how often the bus arrives more than 2 or 5 minutes later
than the estimate the planner would have used to time the next connection. Writes
outputs/advisor/corridor_evaluation.json. Coverage is one segment and one day: it is not system-wide accuracy.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IST = timezone(timedelta(hours=5, minutes=30))
LATE_THRESHOLDS = (2, 5)


def metrics(estimate: np.ndarray, actual: np.ndarray) -> dict:
    error = estimate - actual
    late = actual - estimate  # positive: the bus arrives after the time the planner assumed
    return {"mae_minutes": float(np.mean(np.abs(error))), "rmse_minutes": float(np.sqrt(np.mean(error ** 2))),
            "bias_minutes": float(np.mean(error)),
            **{f"late_over_{t}_min_percent": float(np.mean(late > t) * 100) for t in LATE_THRESHOLDS}}


def evaluate(holdout: pd.DataFrame, segment: str, timetable_minutes: float, champion: int) -> dict:
    rows = holdout[holdout["segment_id"] == segment].copy()
    rows["hour"] = [datetime.fromtimestamp(t, IST).hour for t in rows["received_at"]]
    actual = rows["actual_minutes"].to_numpy(float)
    estimates = {"timetable": np.full(len(rows), timetable_minutes),
                 "historical_median": rows[f"baseline_for_v{champion}"].to_numpy(float),
                 f"model_v{champion}": rows[f"pred_v{champion}"].to_numpy(float)}
    peak = rows["hour"].isin([8, 9, 10, 17, 18, 19, 20]).to_numpy()
    out = {"segment": segment, "traversals": int(len(rows)), "observed_mean_minutes": float(actual.mean()),
           "observed_range_minutes": [float(actual.min()), float(actual.max())],
           "timetable_minutes": timetable_minutes, "estimators": {}}
    for name, values in estimates.items():
        out["estimators"][name] = {"all": metrics(values, actual)}
        if peak.any() and (~peak).any():
            out["estimators"][name]["peak"] = {**metrics(values[peak], actual[peak]), "traversals": int(peak.sum())}
            out["estimators"][name]["off_peak"] = {**metrics(values[~peak], actual[~peak]), "traversals": int((~peak).sum())}
    return out


def main() -> int:
    from advisor.network import load_network
    from advisor.planner import Advisor

    registry = ROOT / "outputs" / "phase3" / "registry"
    ledger = json.loads((registry / "model_versions.json").read_text(encoding="utf-8"))
    champion = int(ledger["aliases"]["champion"])
    holdout = pd.read_csv(registry / "holdout_predictions.csv")
    adv = Advisor(load_network(), online_places=False, online_routing=False)
    segment = adv.cfg["bus_model"]["segment_id"]
    result = evaluate(holdout, segment, adv.corridor_timetable_minutes(), champion)
    result.update(generated_at=datetime.now().astimezone().isoformat(timespec="seconds"), champion_version=champion,
                  holdout_day="2019-07-08", source="outputs/phase3/registry/holdout_predictions.csv",
                  note="One segment, one held-out day; peak = 08-10 h and 17-20 h IST departures.")
    out = ROOT / "outputs" / "advisor" / "corridor_evaluation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{segment}: {result['traversals']} observed traversals on 2019-07-08, mean {result['observed_mean_minutes']:.2f} min")
    print(f"{'estimate':20} {'MAE':>6} {'RMSE':>6} {'bias':>6} {'late>2':>7} {'late>5':>7}")
    for name, m in result["estimators"].items():
        a = m["all"]
        print(f"{name:20} {a['mae_minutes']:6.2f} {a['rmse_minutes']:6.2f} {a['bias_minutes']:+6.2f} "
              f"{a['late_over_2_min_percent']:6.1f}% {a['late_over_5_min_percent']:6.1f}%")
    print(f"Wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
