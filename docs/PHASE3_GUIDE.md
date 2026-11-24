# Phase 3 guide: run, demonstrate and explain

Phase 3 requirements and where each is met:

| Requirement | Delivered by | Evidence produced |
|---|---|---|
| 1. Induce data/model drift; show detection and monitoring | `src/monitoring/` + `config/phase3/monitoring_policy.json` | `outputs/phase3/monitoring/<scenario>/` (events, windows, feature drift, CUSUM, alerts) |
| 2. Model versioning and the reason for it | `src/versioning/` + `config/phase3/promotion_policy.json` | `outputs/phase3/registry/` (ledger, audit log, lifecycle report, artifacts), Phase 3 MLflow registry |
| 3. Complete dashboard of the MLOps pipeline | `dashboard/web/` (React) + `dashboard/server.py` (API) | Web app at `http://127.0.0.1:8050` |
| 4. Governance and its justification | `docs/PHASE3_GOVERNANCE.md`, `docs/MODEL_CARD.md` | Dashboard → Governance page |

Nothing in Phase 3 modifies the live Phase 2 container, its MLflow registry (`outputs/phase2_registry`) or the GHCR image.

## 1. Prerequisites

- The existing development environment `.venv-dev` (CPython 3.12, `requirements-dev.lock.txt`).
- The Phase 2 inputs already on this laptop: `data/processed/phase2_cold_start/traversals.csv` (637 rows) and the approved bundle `outputs/phase2_serving/`.

## 2. Run the Phase 3 pipeline (about a minute)

```powershell
.\.venv-dev\Scripts\Activate.ps1
python -m pytest tests/test_phase3_monitoring.py tests/test_phase3_versioning.py tests/test_phase3_dashboard.py -q
$env:MLOPS_ACTOR = "your-name"
python -m scripts.run_phase3 --write-evidence
```

What it does:

1. Loads the **approved v1** artifact with the Phase 2 hash checks.
2. Replays 5 and 8 July through v1 under four scenarios (natural, demand shift, road works, timezone fault) and writes the monitoring evidence.
3. Creates the version ledger: imports v1, retrains v2 because of the natural performance alarm, gates and promotes it, trains v3 on a corrupted batch (rejected), runs a rollback drill, exports the v2 serving bundle, and mirrors everything into `outputs/phase3/registry/mlflow.db`.
4. Writes `outputs/phase3/phase3_summary.json`. With `--write-evidence` it also writes `docs/results/phase3/phase3_summary.json`, which is small and path-free, so you can commit it.

The ledger is append-only. A second run into the same folder is refused, so use `--output-dir outputs/phase3-run2` for a fresh run. `--no-mlflow` skips the MLflow mirror. `--reproduce-v1` refits v1 when the approved bundle is unavailable, and the substitution is recorded.

## 3. Open the dashboard

The dashboard is a React app (Vite) served by a small Python API that reads the pipeline artifacts. The API runs in `.venv-dev` with no extra Python packages. Building the React app needs [Node.js](https://nodejs.org) 18 or newer, once:

```powershell
cd dashboard\web
npm install
npm run build
cd ..\..
python -m dashboard.server
```

Open `http://127.0.0.1:8050`. After the one-time build, only `python -m dashboard.server` is needed, and the demo works offline. Use **Refresh** in the top bar after re-running the pipeline, and the button at the bottom of the sidebar to switch between dark and light themes (light projects better).

For live editing of the UI, keep the server running and start `npm run dev` in `dashboard\web`, then open `http://localhost:5173`; API calls are forwarded to the server.

## 4. Optional: MLflow UI and serving v2

```powershell
# Phase 3 registry with champion/previous aliases (the exact command is in lifecycle_report.json → mlflow.ui_command)
mlflow ui --backend-store-uri "sqlite:///$((Resolve-Path outputs/phase3/registry/mlflow.db).Path -replace '\\','/')" --port 5002

# Serve the v2 champion with the unchanged FastAPI code, next to the live v1 container on 8001
$env:BUS_MODEL_BUNDLE_DIR = "outputs/phase3/serving/v2"
python -m uvicorn src.api.main:app --port 8002
```

On the dashboard's Deployment page, probe `http://127.0.0.1:8001` (v1 container) and `http://127.0.0.1:8002` (v2) to record health and latency. `/health` reports `model_version` 1 or 2.

## 5. Faculty demonstration sequence (about 12 minutes)

1. **Overview:** the 11/11 ring, the six KPIs and the "what each scenario triggered" cards set the story in one screen.
2. **Pipeline:** walk the three lanes (data foundation, build and ship, operate and improve). Every green card is read from a real artifact.
3. **Drift monitor → Natural replay:** "No injection. 5 July is the day v1 was approved on, so it must stay quiet, and it does. On 8 July the MB Road westbound detector alarms at 15:33. That is real drift in the 2019 data."
4. **Road works:** "Inputs are unchanged, so the input-drift rows stay green. Only the error-based CUSUM catches it, 49 minutes after the first slowed bus. This is why we monitor delayed labels." Hover the charts to show individual trips.
5. **Timezone fault:** "Per-request validation catches it 12 minutes after the first bad request. Hour features then drift because the clock is wrong. We quarantine the data instead of retraining on it."
6. **Demand shift:** "Inputs drift, yet overall error falls. So input drift alone never triggers retraining." Click the 8 Jul morning-rush column to show the PSI bars.
7. **Model registry:** show v1/v2/v3, the v2 gate (7/7 passed), the v3 gate (data validation failed), the version diff (only the data window changed), MAE by segment, and the audit log with its hash chain.
8. **Deployment:** run the live health check; compare v1 and v2 predictions for 8 July 17:10 on Route 90.
9. **Governance:** the controls table, then open the governance policy and explain proportionate governance.

## 6. How to explain the key ideas

- **Data drift vs model drift:** data drift means the inputs change (who asks, when, how). Model (concept) drift means the relationship between inputs and riding time changes (road works, monsoon). The first can be measured immediately; the second needs labels, which arrive when the bus exits.
- **Why PSI thresholds are resampled:** a window of 15 trips can look "different" by chance. We measure how different in-control windows of that size usually look and alert only beyond the 99th percentile.
- **Why CUSUM:** it accumulates small, consistent excess errors over time. A single bad trip is ignored; a sustained 50% increase triggers an alarm. Dividing by the error expected for that segment and time of day keeps congested afternoons from looking like drift.
- **Why a version ledger plus MLflow:** MLflow gives the team's familiar registry UI and aliases. The ledger adds the governance record (reason, trigger, gate results, data hash) and an audit chain that works even when MLflow is unavailable.

## 7. Verification status

- **Release-environment run (21 November 2026, Windows, Python 3.12.14, scikit-learn 1.5.2):** the pipeline completed with the approved v1 artifact (sha256 `b26d1a45…`). All three versions were registered in the Phase 3 MLflow store with `champion` → v2 and `previous` → v1. The rollback drill reproduced the Phase 2 release prediction exactly (6.3204 min), and the audit chain verified intact (9 entries). Results: `docs/results/phase3/phase3_summary.json`.
- **React dashboard:** built with Vite 5.4.11 on Windows and served by `dashboard.server`. Every page was also rendered in headless Chromium, in dark and light themes, with no console errors.
- **Tests:** the Phase 3 tests pass on synthetic fixtures and run in the existing Windows/Linux CI with the locked versions.
