"""Delhi multimodal sustainable transport advisor - API + web app (separate from the MLOps dashboard).

    python -m advisor.server              # http://127.0.0.1:8070
    python -m advisor.server --port 8071

Needs data/processed/advisor/ (python -m scripts.advisor_fetch_data, then python -m scripts.advisor_build_network).
Reads the approved bus model bundle read-only; never writes to outputs/.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if sys.version_info < (3, 10):
    sys.exit(f"The advisor needs the project's Python 3.12 environment; this is Python {sys.version.split()[0]}.\n"
             f"Run it with:  .\\.venv-dev\\Scripts\\python.exe -m advisor.server")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.applications import Starlette  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from advisor.ingest import OUT_DIR  # noqa: E402
from advisor.network import load_network  # noqa: E402
from advisor.planner import IST, PRIORITIES, Advisor, PlanError  # noqa: E402

WEB_DIST = ROOT / "advisor" / "web" / "dist"
DEFAULT_PORT = 8070


def _error(status: int, code: str, message: str, hint: str | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "hint": hint}}, status_code=status)


def create_app(network_dir: Path = OUT_DIR, web_dist: Path = WEB_DIST, advisor: Advisor | None = None) -> Starlette:
    state: dict = {"advisor": advisor, "load_error": None}

    def get_advisor() -> Advisor | None:
        if state["advisor"] is None and state["load_error"] is None:
            try:
                state["advisor"] = Advisor(load_network(network_dir))
            except Exception as exc:  # reported by /api/health
                state["load_error"] = f"{type(exc).__name__}: {exc}"
        return state["advisor"]

    async def health(_: Request):
        adv = await run_in_threadpool(get_advisor)
        if adv is None:
            return JSONResponse({"status": "unavailable", "error": state["load_error"],
                                 "fix": "python -m scripts.advisor_fetch_data && python -m scripts.advisor_build_network"},
                                status_code=503)
        meta = adv.net.meta
        return JSONResponse({
            "status": "ready", "counts": meta["counts"],
            "bus_model": adv.bus_model.info(),
            "geocoder": adv.places.online_status,
            "cab_routing": adv.cab.status,
            "cab_types": {k: v["label"] for k, v in adv.cfg["cab"]["types"].items()},
            "priorities": list(PRIORITIES),
            "sources": [{"key": k, "title": v["title"], "publisher": v["publisher"], "vintage": v["vintage"],
                         "notes": v["notes"], "url": v["official_page"]} for k, v in meta["sources"].items()],
            "assumptions": {"walking": adv.cfg["walking"], "transfer_buffers_min": adv.cfg["transfer_buffers_min"],
                            "fares": adv.cfg["fares"], "emissions_kg_per_pkm": adv.cfg["emissions_kg_per_pkm"],
                            "cab": {k: adv.cfg["cab"][k] for k in ("types", "traffic_factor", "fare_source", "fallback", "min_cab_km")}},
        })

    async def places(request: Request):
        adv = await run_in_threadpool(get_advisor)
        if adv is None:
            return _error(503, "not_ready", "The network is not built yet.", state["load_error"])
        q = request.query_params.get("q", "")[:80]
        online = request.query_params.get("online") != "0"
        results = await run_in_threadpool(adv.search_places, q, 10, online)
        return JSONResponse({"results": results, "online": adv.places.online_status["state"]})

    async def reverse(request: Request):
        adv = await run_in_threadpool(get_advisor)
        if adv is None:
            return _error(503, "not_ready", "The network is not built yet.", state["load_error"])
        try:
            lat, lon = float(request.query_params["lat"]), float(request.query_params["lon"])
        except (KeyError, ValueError):
            return _error(422, "bad_point", "lat and lon are required numbers.")
        online = request.query_params.get("online") != "0"
        return JSONResponse(await run_in_threadpool(adv.reverse, lat, lon, online))

    async def model(request: Request):
        adv = await run_in_threadpool(get_advisor)
        if adv is None:
            return _error(503, "not_ready", "The network is not built yet.", state["load_error"])
        try:
            day = datetime.fromisoformat(request.query_params.get("date") or datetime.now(IST).strftime("%Y-%m-%d"))
        except ValueError:
            return _error(422, "bad_date", "date must look like 2026-11-23.")
        day = day.replace(tzinfo=IST)
        bm = adv.bus_model
        profile = await run_in_threadpool(bm.day_profile, day) if bm.available else []
        return JSONResponse({**bm.info(), "date": day.strftime("%Y-%m-%d"), "profile": profile,
                             "timetable_minutes": adv.corridor_timetable_minutes(),
                             "segment_km": round(bm.segment.length_km, 2) if bm.segment else None})

    async def network(_: Request):
        adv = await run_in_threadpool(get_advisor)
        if adv is None:
            return _error(503, "not_ready", "The network is not built yet.", state["load_error"])
        net = adv.net
        stations = [{"name": net.names[i], "lat": float(net.lat[i]), "lon": float(net.lon[i]),
                     "mode": "metro" if net.mode[i] == 1 else "rail"} for i in range(net.n_stops) if net.mode[i] != 0]
        return JSONResponse({"metro_lines": net.meta["metro_shapes"], "stations": stations,
                             "area": adv.cfg["service_area"],
                             "boundary": [[p[1], p[0]] for p in adv.places.boundary],
                             "corridor": adv.corridor_geometry()})

    async def plan(request: Request):
        adv = await run_in_threadpool(get_advisor)
        if adv is None:
            return _error(503, "not_ready", "The network is not built yet.", state["load_error"])
        try:
            body = await request.json()
        except Exception:
            return _error(400, "bad_json", "The request body must be JSON.")
        if not isinstance(body, dict):
            return _error(400, "bad_json", "The request body must be a JSON object.")
        try:
            depart = datetime.fromisoformat(str(body.get("depart") or datetime.now(IST).strftime("%Y-%m-%dT%H:%M")))
        except ValueError:
            return _error(422, "bad_time", "Departure time must look like 2026-11-23T09:00.")
        budget = body.get("budget_inr")
        try:
            budget = None if budget in (None, "") else float(budget)
            max_walk = body.get("max_walk_m")
            max_walk = None if max_walk in (None, "") else min(2000.0, max(200.0, float(max_walk)))
        except (TypeError, ValueError):
            return _error(422, "bad_number", "Budget and walking distance must be numbers.")
        try:
            result = await run_in_threadpool(
                adv.plan, body.get("origin"), body.get("destination"), depart, budget,
                str(body.get("priority") or "balanced"), bool(body.get("women_free_bus")),
                bool(body.get("smart_card")), max_walk,
                [str(m) for m in body["modes"]] if isinstance(body.get("modes"), list) else None,
                str(body.get("cab_type") or "taxi_ac"))
        except PlanError as exc:
            return _error(422, exc.code, exc.message, exc.hint)
        return JSONResponse(result)

    async def spa(request: Request):
        index = web_dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return PlainTextResponse("Advisor API is running. Build the web app: cd advisor/web && npm install && npm run build",
                                 status_code=200)

    routes = [Route("/api/health", health), Route("/api/places", places), Route("/api/network", network),
              Route("/api/plan", plan, methods=["POST"]), Route("/api/reverse", reverse), Route("/api/model", model)]
    if (web_dist / "assets").exists():
        routes.append(Mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets"))
    routes.append(Route("/{path:path}", spa))
    return Starlette(routes=routes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Delhi multimodal transport advisor")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    import uvicorn

    print(f"Delhi transport advisor: http://{args.host}:{args.port}  (API: /api/health)")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
