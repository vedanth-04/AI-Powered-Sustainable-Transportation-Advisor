"""Backend for the React MLOps dashboard: JSON from the pipeline artifacts + the built web app.

    python -m dashboard.server            # http://127.0.0.1:8050
    python -m dashboard.server --port 8060 --phase3-dir outputs/phase3-run2

Runs in the existing development environment (.venv-dev): Starlette and Uvicorn come with FastAPI.
It only reads artifacts, except that health-check results are appended to service_checks.jsonl.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if sys.version_info < (3, 12):
    sys.exit(f"The dashboard API needs the project's Python 3.12 environment; this is Python {sys.version.split()[0]} "
             f"({sys.executable}).\nRun it with:  .\\.venv-dev\\Scripts\\python.exe -m dashboard.server")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.applications import Starlette  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from dashboard import data as D  # noqa: E402
from dashboard import payloads as P  # noqa: E402

WEB_DIST = ROOT / "dashboard" / "web" / "dist"


def create_app(phase3_dir: Path | None = None, web_dist: Path = WEB_DIST) -> Starlette:
    folder = Path(phase3_dir or os.environ.get("PHASE3_DIR", D.PHASE3))
    if not folder.is_absolute():
        folder = ROOT / folder

    async def state(request: Request) -> JSONResponse:
        return JSONResponse(await run_in_threadpool(P.build_state, ROOT, folder))

    async def scenario(request: Request) -> JSONResponse:
        payload = await run_in_threadpool(P.build_scenario, folder, request.path_params["name"])
        if payload is None:
            return JSONResponse({"error": "Unknown scenario or replay not run yet."}, status_code=404)
        return JSONResponse(payload)

    async def service_check(request: Request) -> JSONResponse:
        body = await request.json()
        url = str(body.get("base_url", "")).strip()
        if not P.allowed_service_url(url):
            return JSONResponse({"error": "Only http://127.0.0.1:<port> or http://localhost:<port> can be probed."},
                                status_code=400)
        result = await run_in_threadpool(D.check_service, url)
        D.append_service_check(folder, result)
        return JSONResponse(P.clean(result))

    async def predict(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            payload = await run_in_threadpool(P.predict_all, folder, str(body["segment_id"]), str(body["date"]),
                                              str(body["time"]))
        except (KeyError, ValueError) as exc:
            return JSONResponse({"error": f"Invalid request: {exc}"}, status_code=400)
        return JSONResponse(payload)

    async def doc(request: Request) -> PlainTextResponse:
        relative = P.DOCS.get(request.path_params["name"])
        if relative is None or not (ROOT / relative).exists():
            return PlainTextResponse("Not found", status_code=404)
        return PlainTextResponse((ROOT / relative).read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "phase3_dir": str(folder), "web_built": (web_dist / "index.html").exists()})

    async def not_built(request: Request):
        index = web_dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return PlainTextResponse(
            "The React app is not built yet. In dashboard/web run:  npm install  then  npm run build\n"
            "(or use  npm run dev  for live reload). The JSON API is running at /api/state.", status_code=503)

    routes = [
        Route("/api/health", health),
        Route("/api/state", state),
        Route("/api/scenario/{name}", scenario),
        Route("/api/service-check", service_check, methods=["POST"]),
        Route("/api/predict", predict, methods=["POST"]),
        Route("/api/doc/{name}", doc),
    ]
    if (web_dist / "assets").is_dir():
        routes.append(Mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets"))
    routes.append(Route("/{path:path}", not_built))
    return Starlette(routes=routes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--phase3-dir", type=Path, default=None)
    args = parser.parse_args()
    import uvicorn

    app = create_app(args.phase3_dir)
    print(f"MLOps dashboard: http://{args.host}:{args.port}  (API: /api/state)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
