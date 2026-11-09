# Phase 2 demonstration and teammate deployment guide

For source/test demonstrations use the new clean setup: `powershell -File scripts/setup_dev.ps1 -RunTests`. Batch A on November 9 passed pip check, exact development pins and 80 tests (23 warnings) in a fresh environment. This supersedes the earlier mixed-environment limitation for development tests; it does not recreate the original real-data registry. Keep the published v1 demonstration below separate.

This guide covers the released `BusTravelTimePredictor` version 1: model tests, quality checks, the MLflow registry, FastAPI inference, Docker packaging, GitHub Actions, and deployment on a Windows PC using Docker Desktop with WSL 2. Run the PowerShell commands from the repository root.

## 1. What is deployed

The approved model is **Gradient Boosting Regressor** using the **`cold_start_v1`** feature policy. Its approved scope is a historical demonstration for Route **`90`**, segment **`ORR_CHIRAG_TO_NEHRU_PLACE_EB`**, eastbound. The API predicts riding time across this road segment in minutes.

The release image is pinned to this digest in `deploy/model-v1.json`:

```text
ghcr.io/vedanth-04/ai-powered-sustainable-transportation-advisor/bus-travel-time@sha256:0250462721176db01d63cd77f93ba7647dd7c94890dc1f7d6e7025e85e2b5dad
```

The image was built from release tag `phase2-image-v1`, source commit `44d31e188ec0e7ad10bf439a4b53f42f0774e63d`. Later deployment and documentation commits can use this same released image. The [successful image release run](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/actions/runs/42330318360) records its publication and verification.

The API currently runs on this project's Windows demonstration host at `http://127.0.0.1:8001`. Each teammate starts an independent instance on their own PC. A localhost URL addresses the computer where the browser runs.

## 2. Tools and the evidence for each requirement

| Phase 2 requirement | Tool used | What to demonstrate |
|---|---|---|
| Model and pipeline testing | Python, Pytest | Current test result and JUnit report; examples from `tests/test_models.py` and `tests/test_api.py` |
| Model risk and quality checks | Python, pandas, scikit-learn, saved JSON/CSV reports | Date separation, candidate versus median, route-level error, positive predictions, reload consistency, artifact hashes, approved scope |
| Experiment tracking | MLflow with SQLite metadata and local artifacts | Recorded model runs, validation/test metrics, parameters, feature policy, and artifacts |
| Model registry | MLflow Model Registry | `BusTravelTimePredictor` version `1`, status `READY`, linked training run and checksum |
| Artifact export | Joblib and SHA-256 verification | The approved registry artifact exported as `model.joblib` with `manifest.json` |
| Inference service | FastAPI, Pydantic, Uvicorn | Readiness, a valid prediction, and invalid requests rejected with HTTP 422 |
| Containerization | Docker Desktop, WSL 2, Docker Compose | A healthy Linux container and its pinned image digest on the local host |
| CI | GitHub Actions, Pytest, Docker | A passing `Phase 2 CI` run for the source commit |
| Image publication | GitHub Actions, GitHub Container Registry (GHCR) | A passing `Phase 2 Model v1 Release` run and fresh-runner verification of the published digest |
| Local deployment and recovery | Python deployment script, Docker Compose | `scripts/deploy_api.py`, readiness/smoke checks, saved deployment state, recovery behavior covered by tests |
| Live verification evidence | Python standard library, Docker inspection, HTTP requests | A newly generated `outputs/phase2_demo/deployment_check.json` |

Git and GitHub hold source and workflow history. DVC and the configured DagsHub remote belong to the project's data-versioning workflow. They are relevant to reproducing training; the published serving image contains the approved model needed to run this deployment.

## 3. Current v1 model results and limits

The source for the following results is `outputs/phase2_release_check/quality_report.json`, checked on **6 November 2026 at 06:55 UTC**. Training observations are from July 2019. These are the cold-start release results; the earlier benchmarking documents describe separate experiments.

A [copy of that quality report](results/phase2-v1/quality_report.json) and a [registry record with the machine-specific tracking URI removed](results/phase2-v1/registration.json) are committed for teammates and reviewers. These are historical approval records. The quality report's `git_head` records the base checkout at evaluation time; its `working_tree_source_sha256` fields record the evaluated source files. The published image's source commit is recorded separately in section 1.

| Split | IST dates | Traversals |
|---|---|---:|
| Train | 1, 2, and 3 July 2019 | 408 |
| Validation | 5 July 2019 | 102 |
| Test | 8 July 2019 | 127 |

The tree candidate was selected using validation MAE. Its validation MAE was **2.474 minutes**, compared with **2.492** for Random Forest and **3.236** for the historical-median baseline. Only the selected tree and baseline are reported on the held-out test split in the release report.

| Test scope | Model | MAE (minutes) | RMSE (minutes) | MAPE (%) |
|---|---|---:|---:|---:|
| All 127 test traversals | Gradient Boosting | 3.623 | 6.320 | 22.04 |
| All 127 test traversals | Historical median | 4.270 | 6.935 | 27.49 |
| Approved Route 90 segment: 36 test traversals | Gradient Boosting | 1.166 | 1.599 | 15.00 |
| Approved Route 90 segment: 36 test traversals | Historical median | 1.303 | 2.128 | 16.08 |

The release quality report records all checks as passing. It includes date-split agreement, cold-start feature consistency, candidate improvement, finite positive predictions, reloaded-model score agreement, and matching logged-artifact hashes. Its Pytest record contains **29 tests** from that release-check stage. Run the current suite separately to report its current test count.

Version 1 is linked to MLflow training run `66c819ceb83740c18d05800213524441`. The approved Joblib artifact SHA-256 is:

```text
b26d1a45f8e97278b8be70eef9c6c88e39b7d52537d55bea6a206b3391934a88
```

Explain these limits during the demonstration:

- The release check repeats previously evaluated 2019 dates in the release environment. It does not establish accuracy on newly collected present-day traffic.
- The approved API scope is the historical Route 90 eastbound segment. Other routes/segments receive HTTP 422.
- Cold-start inference uses the evaluated policy without observed traversal history for the request. It does not consume a live GPS feed.
- The prediction covers segment riding time. Current timetable-to-gate mapping and present-day service accuracy remain unevaluated.
- A successful HTTP prediction verifies serving behavior. Accuracy is supported by the historical held-out evaluation above.

## 4. Start or verify the local deployment

Start Docker Desktop and wait for its Linux engine to become ready. Use PowerShell on Windows; WSL 2 provides the Docker backend.

```powershell
docker version
docker compose version
```

For a new deployment use Python 3.12 below. If this Compose project is already running, use its existing state directory; the November 9 laptop uses the custom path in [section 12](#12-november-9-laptop-verification-and-faculty-sequence).

```powershell
py -3.12 -m scripts.deploy_api --port 8001
py -3.12 -m scripts.verify_deployment
```

The deploy command pulls the pinned image, starts the dedicated Compose service, waits for readiness, checks the approved prediction and unsupported-route rejection, and records the active release in `outputs/phase2_deploy/state.json`. Running it again with the same release is supported. If an activated update fails its checks, the helper attempts to restore and verify the preceding active release. The failure/recovery paths have automated tests in `tests/test_deploy.py`.

The verification command inspects the deployment and sends live HTTP requests. It saves `outputs/phase2_demo/deployment_check.json` and exits with a nonzero status on a mismatch. This command does not retrain or redeploy the model. Keep its timestamp with the demonstration evidence.

Open [Swagger UI](http://127.0.0.1:8001/docs). Expand `GET /health`, choose **Try it out**, then **Execute**. A ready response reports `BusTravelTimePredictor`, model version `1`, and `cold_start_v1`.

Expand `POST /predict/bus` and submit:

```json
{
  "segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB",
  "route_id": "90",
  "entry_at": "2019-07-08T17:10:00+05:30"
}
```

The released model returns approximately **6.320402254818158 minutes**, model version `1`, estimate source `model`, and history policy `cold_start_v1`. Change `route_id` to `999` and repeat to show HTTP 422. Restore Route 90 afterwards.

If port 8001 is occupied, choose an available port when deploying. The verifier reads the deployed port from the saved state; open Swagger UI at that port.

## 5. Show current tests and historical quality evidence

Use the development environment with test dependencies installed:

```powershell
New-Item -ItemType Directory -Force outputs/phase2_demo | Out-Null
.\.venv\Scripts\python.exe -m pytest tests -q --junitxml=outputs/phase2_demo/pytest.xml
Get-Content docs/results/phase2-v1/quality_report.json
Get-Content docs/results/phase2-v1/registration.json
```

On the November 9 laptop, the original virtual environment deliberately remains unchanged and does not have pytest. Show the actual 80-test run in outputs/local_setup/project-audit-20261109-132719/pytest-final.xml and pytest-final.log. The final mixed test environment passes fixtures but still fails pip check; it is not a release-approval environment.

Show the latest test result separately from the earlier 29-test release-quality record. Explain one date-split/feature test, one API validation test, and one failed-deployment recovery test. This connects the tests to model reliability and deployment behavior.

The `outputs` directory is ignored and machine-specific. New clones include historical quality/registry snapshots, not the original training data or MLflow database. The [single-command reproduction workflow](phase2_reproduction.md) has existed since November 7; it still requires the 637-row processed input. Do not retrain for a classroom serving check. The original v1 snapshot predates the current approval schema and cannot be passed unchanged to the current registrar.

## 6. Open the correct MLflow registry

Only on a machine that actually has the original registry and artifacts, start MLflow against the Phase 2 SQLite database. A plain `mlflow ui` can open a different default store.

```powershell
$registryPath = (Resolve-Path outputs/phase2_registry/tracking.db).Path.Replace('\', '/')
.\.venv\Scripts\mlflow.exe ui --backend-store-uri "sqlite:///$registryPath" --host 127.0.0.1 --port 5000
```

This database is absent on the November 9 laptop. Use the committed registry/quality snapshots and the historical PDF screenshot there; do not present a new empty database as the original registry. Fixture-based registry tests are a separate executable demonstration.

Keep this terminal running and open [MLflow](http://127.0.0.1:5000). Show the recorded cold-start model runs and their metrics. Open **Models**, then **BusTravelTimePredictor**, version **1**. Check the linked training run against `66c819ceb83740c18d05800213524441`, and show the registered artifact/checksum metadata.

The serving image already contains the exported model and manifest. The local inference container can run independently of this dashboard. Teammates who only run the released API need the published image; reproducing the training/registry demonstration requires the corresponding data and local MLflow artifacts.

## 7. Show CI and release automation

Open the repository's [Actions page](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/actions).

1. Open a successful **Phase 2 CI** run for the branch/commit being demonstrated. Show Pytest, synthetic-bundle preparation, Docker build, and HTTP smoke-test steps. The workflow runs for pushes to `main` or `phase2/model-quality`, pull requests, and manual workflow dispatch.
2. Explain that CI creates a synthetic test model with an expected **6.25-minute** prediction. This checks API/build behavior in a fresh checkout using a controlled fixture.
3. Open the successful **Phase 2 Model v1 Release** run. It requires successful CI on the exact tagged commit, restores the approved bundle from encrypted Actions secrets, verifies file hashes, builds the Linux image, tests the real **6.3204-minute** prediction, and publishes to GHCR.
4. Show the **Verify the published image by digest** job. A fresh runner pulls the published digest and repeats the real-model HTTP checks.
5. Show `deploy/model-v1.json` locally and the newly generated deployment verification report. The image reference connects the published release to the running local service.

**Automation boundary:** GitHub Actions automates CI, image publication, and verification of the published image. The workstation deployment is started by running `scripts.deploy_api.py` locally. There is currently no automatic GitHub Actions connection that deploys new commits to this Windows PC. Describe the demonstration as CI and automated image release followed by a manually initiated, scripted local deployment.

The release workflow is specifically configured for tag `phase2-image-v1`. Treat the existing tag and image digest as the v1 release record. Future model versions require their own reviewed release configuration and approval evidence.

## 8. Teammate setup from a fresh clone

The current release image targets **Linux/amd64**, suitable for the project's x64 Windows/WSL 2 demo setup. Other CPU architectures need compatible Docker emulation or a future image build for their platform.

Install Git, Python 3.12, and Docker Desktop. Enable WSL 2 and Linux containers on Windows, then start Docker Desktop.

```powershell
git clone https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor.git
cd AI-Powered-Sustainable-Transportation-Advisor
py -3.12 --version
docker version
docker compose version
```

The deployment and verification helpers use Python's standard library. They can run with Python 3.12 directly; installing the full training environment is a separate task. If the `py` launcher is unavailable, use the installed Python 3.12 executable in its place.

If the GHCR package requires authentication, each teammate needs access to the package and their own suitable GitHub credentials. A classic personal access token with `read:packages` is the documented authentication method for pulling private packages. Run this interactive command and enter the token at the password prompt:

```powershell
docker login ghcr.io --username YOUR_GITHUB_USERNAME
```

Keep tokens out of chat, source files, and screenshots. Public packages support anonymous pulls. Repository access and package access can be configured separately; consult the [official GHCR access and authentication instructions](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

Deploy and verify:

```powershell
py -3.12 -m scripts.deploy_api --port 8001
py -3.12 -m scripts.verify_deployment
```

Open [the teammate's local Swagger UI](http://127.0.0.1:8001/docs) and use the sample request in section 4. The released image supplies the model and Python inference dependencies. A teammate can demonstrate predictions using this image without first running training or the local model exporter.

## 9. Evidence to collect before class

| Evidence | What it should establish |
|---|---|
| Latest Pytest terminal result and `outputs/phase2_demo/pytest.xml` | Current source tests passed; record the actual count and date |
| `quality_report.json` and the v1 results table in this guide | Historical evaluation and passing release checks, with dates and scope |
| MLflow run comparison and model version 1 screenshot | Experiment tracking and numbered registry linkage |
| Swagger valid prediction screenshot | Real released-model response, version, and units |
| Swagger unsupported-route screenshot | HTTP 422 outside the approved scope |
| Docker Desktop/container status screenshot | The local service is running and healthy |
| Successful CI and release run links/screenshots | Automated tests, build, publication, and digest verification |
| Fresh `outputs/phase2_demo/deployment_check.json` | Observed local runtime checks and deployed image identity |

Local runtime verification and historical model evaluation are separate evidence. Preserve the timestamps and identify which result each screenshot/report supports. Record rollback recovery as test coverage unless you also perform and capture a controlled live rollback demonstration.

## 10. Suggested classroom explanation

“We trained a median baseline, Random Forest, and Gradient Boosting using date-separated historical bus traversals. Gradient Boosting was selected on validation error. The release quality checks verified the feature policy, historical error, positive predictions, reload behavior, and artifact checksums. We registered the approved model as version 1 in MLflow, exported it using Joblib, and served it through FastAPI. Docker packages the model and inference dependencies. GitHub Actions tests the source, builds and verifies the serving image, and publishes the approved release to GHCR. We then run the scripted deployment on this Windows PC and verify the pinned image and HTTP responses. This release demonstrates the historical Route 90 eastbound segment.”

## 11. Captured demonstration report

The [nine-page evidence PDF](../output/pdf/Phase_2_Demonstration_Evidence.pdf) contains the recorded 58-test result, eight runtime checks, historical model evaluation, and real screenshots of readiness, successful prediction, request rejection, MLflow registry version 1, Docker, CI, and image release. Its timestamps distinguish the original checks from the later report assembly. The MLflow screenshot uses a dashboard backed by a copy of the local registry, on port 5001. The original registry was checked separately in read-only mode.

On the original demo machine, raw screenshots and JSON/JUnit inputs are under `outputs/phase2_demo`. These generated files stay outside Git. The PDF is self-contained and can be shared with teammates from this branch. The MLflow dashboard is a temporary local demonstration process; start the UI again when needed using the command in section 6.

To regenerate this report after collecting the input files, use a reporting environment with ReportLab installed:

```powershell
python -m pip install reportlab
python -m scripts.build_demo_report
```

ReportLab is a document-generation dependency. The inference container and standard-library deployment helpers keep their existing dependencies. The report generator reads existing evidence and does not execute tests or collect fresh observations. It needs `deployment_check.json`, `registry_check.json`, `ci_run.json`, and `pytest.xml` in `outputs/phase2_demo`, plus the historical approval snapshots. Screenshots are read from `outputs/phase2_demo/screenshots`: `api_health.jpg`, `api_prediction.jpg`, `api_rejection.jpg`, `mlflow_registry.jpg`, `docker_container.png`, `github_ci.jpg`, and `github_release.jpg`. A missing screenshot is explicitly marked in the generated report. Inspect a regenerated PDF before presenting it.


## 12. November 9 laptop verification and faculty sequence

Vedanth completed the local Docker setup and verification on November 9, 2026, after safely updating `main` to `2358995`. This is distinct from the implementation commits authored as `Vikasyk` in Git and from the November 6-7 historical evaluation. [Tracked sanitized record](results/2026-11-09-validation/summary.json); raw, preserved evidence remains in ignored `outputs/local_setup/verification-20261109-131834/`.

Observed: Docker Desktop 4.99.0, Engine 29.9.3 Linux/amd64, Compose 5.7.0; healthy container; approved GB v1 artifact hash; `cold_start_v1`; eight deployment checks passed; real prediction `6.320402254818158` minutes; unsupported requests returned 422. No interactive GHCR login was needed during that pull; anonymous package access was not established. This is localhost inference, not public production deployment.

The container was left running. To verify it without redeploying or overwriting earlier evidence, from the repository root:

```powershell
# Only if Docker is not already on PATH (per-user installation):
$dockerBin = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'
if (Test-Path $dockerBin) { $env:PATH = "$dockerBin;$env:PATH" }
$stateFile = 'outputs/local_setup/verification-20261109-131834/deployment_state/state.json'
$checkFile = 'outputs/local_setup/deployment-check-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json'
py -3.12 -m scripts.verify_deployment --state-file $stateFile --output $checkFile
py -3.12 -m scripts.smoke_api --base-url http://127.0.0.1:8001 --model-version 1 --expected-minutes 6.320402254818158
Invoke-RestMethod http://127.0.0.1:8001/health
```

Do not run the default deployment command against this existing Compose project: its state is intentionally isolated. If a redeploy is necessary, keep the same state directory with `--state-dir outputs/local_setup/verification-20261109-131834/deployment_state`. A fresh clone on another PC should use section 8 instead.

### Faculty walkthrough (about 10 minutes)

1. **Problem and scope:** show the README and Phase 1 slides. Explain multimodal planning as the proposed product; today's model predicts one segment's riding time, excluding access, waiting and transfers.
2. **History and data:** open the [chronology](summaries/pipeline_overview.md), DVC pointer and corrected EDA. Show `git log --date=short --format="%h %ad %an %s"`; verify the sample with `Get-FileHash data/raw/2019-07-01.db -Algorithm MD5`. Do not expose local DVC credentials.
3. **Labels and model comparison:** show entry/exit gate code, 12 inputs and the [corrected Phase 1 CSV](results/2026-10-16-corrected/model_comparison.csv). Explain why the older 0.62-minute score is superseded. Then show the separate Phase 2 quality/registry snapshots and cold-start policy. Selection used validation MAE; historical test accuracy is not current-traffic accuracy.
4. **Tests and registry:** show the actual November 9 result (80 passed, 61 warnings after isolated dependency alignment, with earlier failed runs retained) and dependency qualifications in the [audit](phase2_submission_checklist.md). Feature parity, cutoff, tampering and temporary-registry fixtures exercise the workflow. Use the original MLflow UI only if its original database exists; otherwise label the [PDF](../output/pdf/Phase_2_Demonstration_Evidence.pdf) registry screenshot as historical evidence.
5. **Live serving:** use the existing-instance verifier/smoke commands above; show Docker Desktop and [Swagger](http://127.0.0.1:8001/docs). Submit the section 4 payload, show model v1, policy and minutes, then change the route to `999` to obtain HTTP 422. A response is a serving check, not an MAE measurement.
6. **Delivery and limits:** open [CI for the inspected main snapshot](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/actions/runs/42342969930), [v1 image release](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/actions/runs/42330318360), and the pinned digest. Explain synthetic CI (6.25) versus the approved real model (6.3204). Show the remaining guide gaps; no protected VM deployment or new production model was performed.

Keep the original PDF's 58-test screenshot, the November 7 documented 80-test reproduction, and November 9's actual suite outcome separate. For the complete requirement status, including failures and blocked reproduction, use the [audit checklist](phase2_submission_checklist.md).

## 13. Alternative source-image build (separate from the faculty serving check)

The original README's source-build procedure is retained here for a machine with an approved export and compatible Python environment. This is not required to run the published image, and it was not executed during the November 9 audit. The original reports, registry and exported bundle are absent on the second laptop; the sanitized committed registry snapshot is not an exporter input.

When the original approved reports and registry are available, `python -m src.models.export_serving_bundle` checks them and exports to `outputs/phase2_serving`. Only after verifying the approved bundle exists, a source-image check can use:

```powershell
Get-FileHash outputs/phase2_serving/model.joblib -Algorithm SHA256
docker build --platform linux/amd64 --tag bus-travel-time:phase2-local .
docker run --rm --name bus-travel-time-source-demo --publish 127.0.0.1:8002:8000 bus-travel-time:phase2-local
# From another terminal, while the foreground container is running:
Invoke-RestMethod http://127.0.0.1:8002/health
```

Compare the model hash to the approved value in section 3 and verify the manifest before building. Use an available port; port 8002 in this example keeps the established 8001 deployment separate. Use Ctrl+C to stop this optional foreground container. Do not generate the synthetic CI bundle for a real-model demonstration, overwrite the approved export, upload release secrets, or recreate the existing `phase2-image-v1` tag as part of routine verification.
