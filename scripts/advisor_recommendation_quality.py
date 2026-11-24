"""Recommendation-quality check: run many random Delhi requests and test every option that comes back.

    .\\.venv-dev\\Scripts\\python.exe -m scripts.advisor_recommendation_quality            # 200 requests
    .\\.venv-dev\\Scripts\\python.exe -m scripts.advisor_recommendation_quality --n 500

The guide's recommendation-quality signals: constraint violations, unreachable transfers, fare
consistency and no-result cases. Requests are random pairs of Delhi ward localities with random
times, budgets, preferences, allowed modes and cab types (fixed seed, offline, so a rerun is identical).
Writes outputs/advisor/recommendation_quality.json; exits non-zero if any option breaks a rule.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advisor.network import load_network  # noqa: E402
from advisor.planner import IST, Advisor, PlanError  # noqa: E402

MODE_SETS = [None, ["bus", "metro", "rail"], ["metro", "cab"], ["bus", "cab"], ["rail", "metro", "cab"], ["bus"], ["metro"]]


def minutes(clock: str) -> int:
    hours, mins = clock[:5].split(":")
    return int(hours) * 60 + int(mins) + (1440 if "+1 day" in clock else 0)


def option_problems(journey: dict, request: dict, cfg: dict) -> list[str]:
    """Every rule an option must satisfy. Each returned string names one broken rule."""
    out = []
    legs, allowed = journey["legs"], set(request["modes"] or ("bus", "metro", "rail", "cab"))
    if not set(journey["modes"]) <= allowed:
        out.append(f"mode not allowed: {sorted(set(journey['modes']) - allowed)}")
    if minutes(journey["leave"]) < request["minute"]:
        out.append("leaves before the requested time")
    if minutes(journey["arrive"]) < minutes(journey["leave"]):
        out.append("arrives before it leaves")
    rides = [leg for leg in legs if leg["type"] == "ride"]
    if abs(sum(leg["fare_inr"] for leg in rides) - journey["fare_inr"]) > 0.01:
        out.append("fare is not the sum of the leg fares")
    if request["budget"] is not None and journey["within_budget"] != (journey["fare_inr"] <= request["budget"] + 1e-9):
        out.append("budget flag disagrees with the fare")
    previous = minutes(journey["leave"])
    for leg in legs:
        if minutes(leg["arrive"]) < minutes(leg["depart"]):
            out.append(f"{leg['type']} leg arrives before it departs")
        if minutes(leg["depart"]) < previous - 1:  # clocks are rounded to the minute
            out.append(f"unreachable connection: {leg['type']} leg departs {leg['depart']} before the previous leg ends")
        if leg.get("wait_minutes", 0) < 0:
            out.append("negative wait")
        previous = minutes(leg["arrive"])
    widest = max(cfg["walking"].get("auto_expand_m") or [cfg["walking"]["max_access_m"]])
    for leg in legs:
        if leg["type"] == "walk" and leg["distance_m"] > widest + cfg["walking"]["max_transfer_m"] + 5:
            out.append(f"walk of {leg['distance_m']} m exceeds every configured walking limit")
    if journey["vehicle_changes"] != max(len(rides) - 1, 0):
        out.append("vehicle change count disagrees with the legs")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    adv = Advisor(load_network(), online_places=False, online_routing=False)
    localities = [place for place in adv.places.localities if place["searchable"]]
    rng = random.Random(args.seed)
    refused, refused_by_modes, problems, seconds, mode_mix = Counter(), Counter(), [], [], Counter()
    options = answered = budget_requests = budget_met = model_options = 0
    for _ in range(args.n):
        a, b = rng.sample(localities, 2)
        hour, minute = rng.choice([5, 6, 7, 8, 9, 10, 12, 15, 17, 18, 19, 20, 21, 22]), rng.choice([0, 15, 30, 45])
        request = {"from": a["name"], "to": b["name"], "day": rng.choice([22, 23, 24, 28]), "minute": hour * 60 + minute,
                   "budget": rng.choice([None, 20, 40, 60]), "priority": rng.choice(["balanced", "cheapest", "fastest", "greenest"]),
                   "modes": rng.choice(MODE_SETS), "cab_type": rng.choice(["taxi_ac", "taxi_non_ac", "auto"])}
        started = time.time()
        try:
            result = adv.plan({"lat": a["lat"], "lon": a["lon"], "label": a["name"]},
                              {"lat": b["lat"], "lon": b["lon"], "label": b["name"]},
                              datetime(2026, 11, request["day"], hour, minute, tzinfo=IST), request["budget"],
                              request["priority"], modes=request["modes"], cab_type=request["cab_type"])
        except PlanError as exc:
            refused[exc.code] += 1
            refused_by_modes[" + ".join(request["modes"] or ["all modes"])] += 1
            continue
        except Exception as exc:  # a crash is a quality failure, not a refusal
            problems.append({"request": request, "problem": f"crash: {type(exc).__name__}: {exc}"})
            continue
        seconds.append(time.time() - started)
        answered += 1
        if request["budget"] is not None:
            budget_requests += 1
            budget_met += any(j["within_budget"] for j in result["journeys"])
        for journey in result["journeys"]:
            options += 1
            mode_mix[" + ".join(sorted(set(journey["modes"])))] += 1
            model_options += journey["uses_bus_model"]
            problems += [{"request": request, "option": journey["id"], "problem": p}
                         for p in option_problems(journey, request, adv.cfg)]
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "requests": args.n, "seed": args.seed,
        "answered": answered, "refused": dict(refused), "refused_by_allowed_modes": dict(refused_by_modes.most_common()),
        "options_checked": options,
        "options_per_answer": round(options / answered, 2) if answered else None,
        "budget_requests": budget_requests, "budget_requests_with_an_option_within_budget": budget_met,
        "options_using_bus_model": model_options, "mode_mix": dict(mode_mix.most_common()),
        "seconds_per_plan": {"mean": round(sum(seconds) / len(seconds), 2), "max": round(max(seconds), 2)} if seconds else None,
        "problems": len(problems), "problem_examples": problems[:25],
        "rules": ["allowed modes only", "never leaves before the requested time", "arrives after it leaves",
                  "fare = sum of leg fares", "budget flag matches the fare", "every leg starts after the previous one ends",
                  "no negative waits", "walks within the configured limits", "vehicle changes = rides - 1"],
    }
    out = ROOT / "outputs" / "advisor" / "recommendation_quality.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{answered}/{args.n} requests answered, refused: {dict(refused)}; {options} options checked against "
          f"{len(report['rules'])} rules; problems: {len(problems)}")
    if report["seconds_per_plan"]:
        print(f"plan time mean {report['seconds_per_plan']['mean']} s, max {report['seconds_per_plan']['max']} s")
    for item in problems[:10]:
        print("  ", item["problem"], "|", item["request"]["from"], "->", item["request"]["to"])
    print(f"Wrote {out.relative_to(ROOT)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
