"""End-to-end check of the Delhi advisor on this machine: data, model governance, prediction parity, geocoder, API.

    .\\.venv-dev\\Scripts\\python.exe -m scripts.advisor_check

Prints PASS/WARN/FAIL lines and exits non-zero on any FAIL. It reads artifacts only.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advisor.network import load_network  # noqa: E402
from advisor.planner import IST, Advisor, PlanError  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def report(status: str, name: str, detail: str) -> None:
    RESULTS.append((status, name, detail))
    print(f"[{status:4}] {name}: {detail}")


def main() -> int:
    t0 = time.time()
    try:
        net = load_network()
    except Exception as exc:
        report("FAIL", "network", f"{exc}")
        return 1
    c = net.meta["counts"]
    report("PASS", "network", f"bus {c['stops']['bus']} stops/{c['trips']['bus']} trips, metro {c['stops']['metro']} stations, "
                              f"rail {c['stops']['rail']} halts/{c['trips']['rail']} trains, places {c.get('places')}")
    adv = Advisor(net)
    info = adv.bus_model.info()
    for s in info["sources"]:
        report("PASS" if s["ok"] else "WARN", f"model source {s['source']}", s["detail"])
    if info["available"]:
        report("PASS", "bus model in use", info["detail"])
    else:
        report("FAIL", "bus model in use", info["detail"])
    parity = info.get("parity") or {}
    status = {True: "PASS", False: "FAIL", None: "WARN"}[parity.get("ok")]
    report(status, "prediction parity with deployed v1", parity.get("detail", "not run"))
    if adv.bus_model.available:
        day = datetime(2026, 11, 23, tzinfo=IST)
        prof = [p for p in adv.bus_model.day_profile(day) if p["minutes"] is not None]
        peak = max(prof, key=lambda p: p["minutes"])
        low = min(prof, key=lambda p: p["minutes"])
        report("PASS", "segment profile", f"{len(prof)} predictions; fastest {low['minutes']} min at {low['time']}, "
                                          f"slowest {peak['minutes']} min at {peak['time']}; timetable assumes "
                                          f"{adv.corridor_timetable_minutes()} min")
    geo = adv.places.online_status
    hits = adv.search_places("India Gate")
    online = [h for h in hits if h.get("source") == "OpenStreetMap"]
    report("PASS" if online else "WARN", "place search (online OSM)",
           f"{len(online)} OpenStreetMap results for 'India Gate'" if online else
           f"offline only ({adv.places.online_status.get('detail')}); ward localities and stops still work")
    hits = adv.search_places("Lajpat Nagar")
    report("PASS" if hits and hits[0]["kind"] == "Locality" else "FAIL", "place search (offline localities)",
           f"first result: {hits[0]['name']} - {hits[0]['detail']}" if hits else "no result")
    rev = adv.reverse(28.6129, 77.2295)
    report("PASS", "reverse geocoding", f"28.6129, 77.2295 -> {rev['name']} ({rev['source']}; locality {rev['locality']})")

    trips = [("Lajpat Nagar", "Karol Bagh", None), ("Chirag Delhi", "Nehru Place Terminal", None), ("Rohini", "Saket", 40)]
    for a, b, budget in trips:
        try:
            o, d = adv.search_places(a)[0], adv.search_places(b)[0]
            t = time.time()
            r = adv.plan(o, d, datetime(2026, 11, 23, 17, 10, tzinfo=IST), budget)
            j = r["journeys"][0]
            uses = sum(x["uses_bus_model"] for x in r["journeys"])
            report("PASS", f"plan {a} -> {b}", f"{len(r['journeys'])} options in {time.time() - t:.1f}s; top: "
                   f"{' + '.join(j['modes'])}, {j['duration_min']} min, Rs {j['fare_inr']}; options using the bus model: {uses}")
        except PlanError as exc:
            report("FAIL", f"plan {a} -> {b}", f"{exc.code}: {exc.message}")
    corridor = next((x for x in RESULTS if x[1] == "plan Chirag Delhi -> Nehru Place Terminal"), None)
    if adv.bus_model.available and corridor and "bus model: 0" in corridor[2]:
        report("WARN", "bus model applied on ORR", "no option on the ORR corridor used the model at 17:10")

    try:
        from starlette.testclient import TestClient
        from advisor.server import create_app

        client = TestClient(create_app(advisor=adv))
        ok = all(client.get(p).status_code == 200 for p in ("/api/health", "/api/network", "/api/model?date=2026-11-23"))
        r = client.post("/api/plan", json={"origin": {"lat": 28.5708, "lon": 77.2365}, "destination": {"lat": 28.6440, "lon": 77.1886},
                                           "depart": "2026-11-23T09:00", "budget_inr": 40})
        report("PASS" if ok and r.status_code == 200 else "FAIL", "HTTP API", f"health/network/model/plan -> {r.status_code}")
    except ImportError as exc:
        report("WARN", "HTTP API", f"not tested ({exc})")

    fails = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    warns = sum(1 for s, _, _ in RESULTS if s == "WARN")
    print(f"\n{len(RESULTS)} checks, {fails} failed, {warns} warnings ({time.time() - t0:.1f}s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
