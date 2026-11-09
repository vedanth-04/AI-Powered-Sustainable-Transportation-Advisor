# AI-Powered Sustainable Transportation Advisor

Predict Delhi bus **segment riding time in minutes** from GPS-derived historical traversals. The broader proposed advisor will compare journey time, cost and estimated emissions; multimodal routing, fares, waiting/transfer estimates and a journey UI remain future milestones.

**Current demo:** Gradient Boosting `BusTravelTimePredictor` v1, `cold_start_v1`, historical Route `90` on `ORR_CHIRAG_TO_NEHRU_PLACE_EB`. This is a local Docker demonstration, not a public production transport service. Other route/segment pairs return HTTP 422.

## Project journey and documentation

| Read | Purpose |
|---|---|
| [Chronological project overview](docs/summaries/pipeline_overview.md) | Phase 1 and Phase 2, actual Git dates/authors, plans versus completed work |
| [Phase 1 EDA](docs/eda_report.md), [labels](docs/label_construction_report.md), [features](docs/feature_engineering_report.md) | Data findings and the batch pipeline inherited by Phase 2 |
| [Corrected Phase 1 benchmark](docs/results/2026-10-16-corrected/README.md) | Measured results after removing target-derived speed leakage |
| [Phase 2 demo guide](docs/phase2_demo.md) | Windows setup, real request, faculty sequence and November 9 laptop verification |
| [Phase 2 requirement audit](docs/phase2_submission_checklist.md) | Every guide requirement, executed checks, limitations and prioritized gaps |
| [Model reproduction](docs/phase2_reproduction.md) | Separate training, approval, registry and export workflow; requires processed data |
| [Team workflow](CONTRIBUTING.md) / [DVC setup](docs/reference/dvc_team_setup.md) | Direct-to-main synchronization and secure data access |
| [Historical reference index](docs/reference/README.md) | Earlier plans/audits retained with their original context |

## Run the published model on Windows

Use Git, Python 3.12 and Docker Desktop with its Linux engine running. The deployment helpers use the Python standard library; running the published image does not require host training dependencies, DVC data or an MLflow server.

From a fresh clone:

```powershell
git clone https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor.git
cd AI-Powered-Sustainable-Transportation-Advisor
docker version
docker compose version
py -3.12 -m scripts.deploy_api --port 8001
py -3.12 -m scripts.verify_deployment
```

Open [Swagger UI](http://127.0.0.1:8001/docs). If GHCR needs authentication, use the interactive login in the [demo guide](docs/phase2_demo.md#8-teammate-setup-from-a-fresh-clone). The image is pinned by digest in [deploy/model-v1.json](deploy/model-v1.json).

**Already running the November 9 laptop deployment?** Its state is in a custom directory. Use the [existing-instance commands](docs/phase2_demo.md#12-november-9-laptop-verification-and-faculty-sequence); do not run a second deployment with the default state directory.

```json
{
  "segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB",
  "route_id": "90",
  "entry_at": "2019-07-08T17:10:00+05:30"
}
```

On November 9, 2026 this laptop returned `6.320402254818158` minutes, model version `1`, policy `cold_start_v1`; the container was healthy and all eight repository deployment checks passed. Invalid requests returned 422. See the [sanitized validation record](docs/results/2026-11-09-validation/summary.json). A successful response verifies serving, not prediction accuracy.

## Keep the experiments separate

| Evidence | Data / policy | Result and interpretation |
|---|---|---|
| Corrected Phase 1, October 16 | 152 traversals; 114/38 chronological split; observed completed-history features | RF MAE 1.8694 min, GB 1.9427, median 2.4412. Small one-day comparison; selection used the holdout. |
| Approved Phase 2 v1, November 6 | 637 traversals; 408/102/127 date splits; `cold_start_v1` | GB selected on validation MAE 2.4739 min; test MAE 3.6226 overall, 1.1661 for the 36 approved-route test rows. Historical accuracy only. |
| November 9 laptop verification | Published v1 image, same documented Route 90 request | HTTP 200, 6.3204 minutes and eight runtime checks. No real-data retraining. |

The old 0.62-minute GB score used target-derived speed and is superseded. The [old benchmark report](docs/model_benchmarking_report.md) and presentation remain historical evidence. The Phase 1 slides also propose XGBoost; this repository implements scikit-learn Gradient Boosting, not XGBoost.

## Data, architecture and reproducibility

Raw source: [Zenodo July 2019 Delhi bus GPS archive](https://zenodo.org/records/21738157/files/july_19_corrected.zip?download=1). The verified daily SQLite sample has 1,977,922 rows, 1,547 buses, 476 routes and 5,194 trips. GPS pings do not contain travel-time labels: the pipeline derives labels from ordered entry/exit gate crossings. Git tracks the [DVC pointer](data/raw/2019-07-01.db.dvc); data, credentials, local model files and MLflow stores stay outside Git. See the [source/usage-terms record](docs/reference/schema_audit_report.md).

```text
SQLite + DVC -> cleaning -> gate-crossing labels -> 12 shared features
  -> median / RF / GB comparison -> quality checks -> local MLflow registry
  -> checked Joblib bundle -> FastAPI -> Docker -> GHCR -> local Compose
```

Code is in `src/data`, `src/features`, `src/models` and `src/api`; orchestration is in `scripts`, tests in `tests`, workflows in `.github/workflows`, and deployment configuration in `deploy`. `docs/results` holds small historical and validation records; `outputs` holds ignored generated evidence. The original two notebooks remain under `notebooks`.

For development, `requirements.txt` declares minimum versions. `requirements-ci.txt` includes the Linux serving lock plus test dependencies. The November 9 attempt to install that lock on Windows failed on unavailable `anyio==4.16.0`; the [audit](docs/phase2_submission_checklist.md) records the fallback test environment. Do not silently substitute dependency versions and claim release parity.

The November 9 fixture suite passed 80 tests with 61 warnings after isolated MLflow/SQLAlchemy alignment. Its mixed test environment still fails dependency checks; the running Linux image independently passes its serving lock and dependency checks.

Run the full existing suite in a prepared test environment with `python -m pytest tests -q`. The [reproduction guide](docs/phase2_reproduction.md) describes fresh output directories and the required 637-row processed input. Do not run training/export into the approved release or replace the live model during a documentation/demo exercise.

## CI, delivery and remaining scope

[CI](.github/workflows/ci.yml) tests code and a **synthetic 6.25-minute fixture**. The [v1 release workflow](.github/workflows/release.yml) checks the approved bundle and real model, publishes GHCR, then pulls and tests the exact digest on a fresh runner. It triggers only on `phase2-image-v1`; do not recreate that existing tag. The [captured evidence PDF](output/pdf/Phase_2_Demonstration_Evidence.pdf) records earlier results/screenshots, not the November 9 test execution.

GitHub Actions automates checks and image release. A local command initiates workstation deployment. Four-segment serving, shared-registry release orchestration, complete baked lineage, structured request logging and protected VM/HTTPS deployment remain gaps against the Phase 2 guide. See the [full requirement matrix](docs/phase2_submission_checklist.md#2-requirement-by-requirement-audit) before claiming Phase 2 is complete.
