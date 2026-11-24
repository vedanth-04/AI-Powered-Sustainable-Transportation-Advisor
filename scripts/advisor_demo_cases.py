"""Run the fixed demo cases through the real Delhi advisor and write the results.

    .\\.venv-dev\\Scripts\\python.exe -m scripts.advisor_demo_cases            # offline: reproducible
    .\\.venv-dev\\Scripts\\python.exe -m scripts.advisor_demo_cases --online   # OSRM road routing for cabs

Writes docs/DEMO_CASES.md (readable) and outputs/advisor/demo_cases.json (every option, every leg).
Each case is a real request on the real network; nothing is hand-edited. The header of the Markdown
file records which bus model source was used, so a run without the model is never mistaken for one with it.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advisor.network import load_network  # noqa: E402
from advisor.planner import IST, Advisor, PlanError  # noqa: E402

MONDAY = (2026, 11, 23)
SUNDAY = (2026, 11, 29)
CASES = [
    {"id": "commute", "title": "Everyday commute, balanced", "from": "Lajpat Nagar", "to": "Karol Bagh", "day": MONDAY,
     "time": "09:00", "shows": "The default request: localities typed by name, all modes, balanced ranking with reasons."},
    {"id": "budget", "title": "Tight budget", "from": "Rohini", "to": "Saket", "day": MONDAY, "time": "17:10",
     "budget_inr": 40, "shows": "Options over the ₹40 budget are flagged and options within it rank first."},
    {"id": "ml_corridor", "title": "Bus on the ML corridor (Outer Ring Road)", "from": "Chirag Delhi",
     "to": "Nehru Place Terminal", "day": MONDAY, "time": "17:10", "modes": ["bus", "metro", "rail"],
     "shows": "The only place the trained bus model is used: Chirag Delhi to Nehru Place eastbound, evening peak."},
    {"id": "greenest", "title": "Greenest preference", "from": "Dwarka", "to": "Rajiv Chowk", "day": MONDAY,
     "time": "08:30", "priority": "greenest", "shows": "Ranking by CO2 per trip; metro beats bus and cab here."},
    {"id": "fastest_cab", "title": "Fastest, cab allowed, far north to south", "from": "Narela", "to": "Saket",
     "day": MONDAY, "time": "18:30", "priority": "fastest",
     "shows": ("Cab feeder joined to the metro, cab only and public transport at evening peak traffic. The fastest "
               "preference still weighs fare, so a much dearer option must save real time to be recommended.")},
    {"id": "night_auto", "title": "Late night by auto-rickshaw", "from": "Najafgarh", "to": "Kalkaji", "day": MONDAY,
     "time": "23:30", "cab_type": "auto", "shows": "Night meter charge (11 pm to 5 am) and the auto-rickshaw tariff."},
    {"id": "women_free", "title": "Women ride DTC/cluster buses free", "from": "Mayur Vihar", "to": "ITO", "day": MONDAY,
     "time": "10:00", "priority": "cheapest", "women_free_bus": True, "smart_card": True,
     "shows": "Pink-ticket free bus travel and the metro smart-card discount change the cheapest option."},
    {"id": "train", "title": "Suburban train in the mix", "from": "Narela (NUR)", "to": "Old Delhi", "day": MONDAY,
     "time": "07:00", "shows": "Northern Railway passenger/MEMU trains (2016 timetable) between two Delhi stations, "
                               "against bus and cab."},
    {"id": "sunday", "title": "Sunday travel", "from": "Hauz Khas", "to": "Kashmere Gate", "day": SUNDAY, "time": "11:00",
     "shows": "Sunday metro fare slabs, and the note that the weekday metro timetable stands in for weekends."},
    {"id": "outside", "title": "Outside the service area", "from_point": {"name": "Cyber City, Gurugram", "lat": 28.4950,
     "lon": 77.0895}, "to": "Karol Bagh", "day": MONDAY, "time": "09:00",
     "shows": "A start outside the Delhi NCT boundary is refused with a clear reason instead of a guessed route."},
]


def place(adv: Advisor, case: dict, role: str) -> dict:
    if f"{role}_point" in case:
        return case[f"{role}_point"]
    hits = adv.search_places(case[role], online=False)
    if not hits:
        raise PlanError("no_place", f"No place called {case[role]!r} was found.")
    return hits[0]


def leg_text(leg: dict) -> str:
    if leg["type"] == "walk":
        return f"walk {leg.get('distance_m', 0)} m"
    if leg.get("mode") == "cab":
        return f"{leg['cab']['type_label']} {leg['distance_km']} km"
    return f"{leg['mode_label']} {leg['route']}"


def run(adv: Advisor, case: dict) -> dict:
    hour, minute = map(int, case["time"].split(":"))
    depart = datetime(*case["day"], hour, minute, tzinfo=IST)
    out = {key: case[key] for key in ("id", "title", "shows")}
    try:
        origin, destination = place(adv, case, "from"), place(adv, case, "to")
        out["request"] = {"from": origin["name"], "to": destination["name"], "depart": depart.isoformat(),
                          **{k: case[k] for k in ("budget_inr", "priority", "women_free_bus", "smart_card", "modes",
                                                  "cab_type") if k in case}}
        started = time.time()
        result = adv.plan(origin, destination, depart, budget_inr=case.get("budget_inr"),
                          priority=case.get("priority", "balanced"), women_free_bus=case.get("women_free_bus", False),
                          smart_card=case.get("smart_card", False), modes=case.get("modes"),
                          cab_type=case.get("cab_type", "taxi_ac"))
        out.update(seconds=round(time.time() - started, 2), notes=result["notes"], budget_status=result["budget_status"],
                   car_baseline_kg_co2=result["car_baseline_kg_co2"], straight_line_km=result["straight_line_km"],
                   journeys=result["journeys"])
    except PlanError as exc:
        out.update(error={"code": exc.code, "message": exc.message, "hint": exc.hint})
        out.setdefault("request", {"from": case.get("from") or case["from_point"]["name"], "to": case["to"],
                                   "depart": depart.isoformat()})
    return out


def markdown(results: list[dict], header: dict) -> str:
    lines = ["# Delhi advisor: demo cases", "",
             f"Generated {header['generated_at']} by `python -m scripts.advisor_demo_cases`"
             f"{' --online' if header['online'] else ''}. Every number below is the advisor's own output for a real "
             "request on the real Delhi network; nothing is edited by hand.", "",
             f"- **Bus model:** {header['bus_model']}",
             f"- **Cab road routing:** {header['cab_routing']}",
             f"- **Network:** {header['network']}", "",
             "| # | Case | From → to | Top option | Time | Fare | CO₂ |", "|---|---|---|---|---|---|---|"]
    for n, r in enumerate(results, 1):
        top = (r.get("journeys") or [None])[0]
        lines.append(f"| {n} | {r['title']} | {r['request']['from']} → {r['request']['to']} | "
                     + (f"{' + '.join(top['modes'])} | {top['duration_min']:.0f} min | ₹{top['fare_inr']:g} | {top['co2_kg']:.2f} kg |"
                        if top else f"refused: `{r['error']['code']}` | – | – | – |"))
    for n, r in enumerate(results, 1):
        q = r["request"]
        extras = [f"{k.replace('_', ' ')}: {v}" for k, v in q.items() if k not in ("from", "to", "depart")]
        lines += ["", f"## {n}. {r['title']}", "", f"*What it shows:* {r['shows']}", "",
                  f"*Request:* {q['from']} → {q['to']}, {datetime.fromisoformat(q['depart']).strftime('%A %d %b %Y, %H:%M')}"
                  + (f"; {'; '.join(extras)}" if extras else "") + "."]
        if "error" in r:
            lines += ["", f"*Result:* refused with `{r['error']['code']}`: {r['error']['message']}"
                      + (f" {r['error']['hint']}" if r["error"].get("hint") else "")]
            continue
        lines += ["", "| Option | Leave → arrive | Time | Fare | CO₂ | Changes | Walk | Route | Bus model |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for i, j in enumerate(r["journeys"], 1):
            tags = f" ({', '.join(j['tags'])})" if j.get("tags") else ""
            route = " → ".join(leg_text(l) for l in j["legs"])
            lines.append(f"| {i}{tags} | {j['leave']} → {j['arrive']} | {j['duration_min']:.0f} min | ₹{j['fare_inr']:g}"
                         f"{'' if j.get('within_budget', True) else ' (over budget)'} | {j['co2_kg']:.2f} kg | "
                         f"{j['vehicle_changes']} | {j['walk_m']} m | {route} | {'yes' if j['uses_bus_model'] else 'no'} |")
        top = r["journeys"][0]
        lines += ["", f"*Why option 1:* {' '.join(top.get('why') or [])}",
                  f"*A car alone would emit about {r['car_baseline_kg_co2']:.2f} kg CO₂; option 1 emits {top['co2_kg']:.2f} kg.*"]
        if r.get("budget_status"):
            lines.append(f"*Budget:* {r['budget_status'].get('message', r['budget_status'])}")
        for note in r["notes"]:
            lines.append(f"> {note}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--online", action="store_true", help="allow OSRM road routing for cab legs")
    parser.add_argument("--markdown", type=Path, default=ROOT / "docs" / "DEMO_CASES.md")
    parser.add_argument("--json", type=Path, default=ROOT / "outputs" / "advisor" / "demo_cases.json")
    args = parser.parse_args()
    net = load_network()
    adv = Advisor(net, online_places=False, online_routing=args.online)
    info = adv.bus_model.info()
    counts = net.meta["counts"]
    header = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "online": args.online,
        "bus_model": (f"v{info['version']} from {info['active_source']}, applied only to {info['segment']}"
                      if info["available"] else f"not available in this environment, so bus times come from the "
                      f"timetable everywhere ({info['detail']})"),
        "cab_routing": "OSRM road routing (public demo server) when reachable" if args.online
                       else "offline rule: straight line x 1.35 at an assumed speed, times a time-of-day traffic factor",
        "network": (f"{counts['stops']['bus']} bus stops / {counts['trips']['bus']} bus trips, "
                    f"{counts['stops']['metro']} metro stations, {counts['stops']['rail']} rail halts"),
    }
    results = []
    for case in CASES:
        result = run(adv, case)
        results.append(result)
        top = (result.get("journeys") or [None])[0]
        print(f"{case['id']:12} " + (f"{len(result['journeys'])} options; top {' + '.join(top['modes'])}, "
                                     f"{top['duration_min']:.0f} min, Rs {top['fare_inr']:g}" if top
                                     else f"refused ({result['error']['code']})"))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps({"header": header, "cases": results}, indent=1, ensure_ascii=False, default=str) + "\n",
                         encoding="utf-8")
    args.markdown.write_text(markdown(results, header), encoding="utf-8")
    print(f"Wrote {args.markdown.relative_to(ROOT)} and {args.json.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
