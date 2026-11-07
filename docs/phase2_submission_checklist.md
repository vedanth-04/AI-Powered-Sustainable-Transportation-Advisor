# Phase 2 submission and team-review checklist

The implemented scope covers model tests, model quality/risk checks, a numbered MLflow registry version, FastAPI inference, Docker packaging, GitHub Actions CI and image publication, and scripted local deployment on Windows with WSL 2.

The API, CI and image-release code reached `main` through earlier pull requests. The later deployment, evidence and reproducible approval additions are on `phase2/model-quality` until their pull request is merged. Use that branch when sharing the complete workflow before the merge. This checklist is a demonstration handoff; it does not merge branches or release another model.

**Final integration:** [PR #3](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/pull/3) carries these remaining additions. Once its status is **Merged**, use `main` for the complete Phase 2 workflow. The repository README provides a fresh-clone deployment quick start. Existing teammates can update a clean `main` checkout with `git switch main` followed by `git pull --ff-only`.

## 1. Material to submit or share

| Item | Location | Purpose |
|---|---|---|
| Project source and changes | GitHub repository and Phase 2 pull request | Review the implementation and commit history |
| Demonstration report | [Evidence PDF](../output/pdf/Phase_2_Demonstration_Evidence.pdf) | Seven actual screenshots with recorded results and scope |
| Full demo sequence | [Demo guide](phase2_demo.md) | Classroom walkthrough and teammate deployment setup |
| Reproducible approval workflow | [Reproduction guide](phase2_reproduction.md) | Repeat tests, training, checks, registration, export and API validation |
| Historical quality approval | [Quality snapshot](results/phase2-v1/quality_report.json) | Model metrics, splits, passing checks and limitations |
| Historical registry record | [Registry snapshot](results/phase2-v1/registration.json) | Model version, training run and approved artifact checksum |
| CI and image-release runs | [GitHub Actions](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/actions) | Successful automated tests, build, publication and published-image checks |

The recorded reproduction on 7 November 2026 passed **80 tests** and **16 quality checks**. It verified the separately registered model against **127 held-out predictions**. The earlier PDF records the preceding 58-test demonstration stage. Keep these timestamps and stages distinct when reporting results.

The released model is Gradient Boosting with `cold_start_v1`, approved for historical Route `90`, eastbound segment `ORR_CHIRAG_TO_NEHRU_PLACE_EB`. The sample prediction is approximately **6.3204 minutes**. Historical error metrics and the sample response serve different purposes; the sample response is not an accuracy metric.

## 2. Prepare the local demo

Start Docker Desktop and wait for the Linux engine to be ready. From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m scripts.deploy_api --port 8001
.\.venv\Scripts\python.exe -m scripts.verify_deployment --output outputs/phase2_submission/deployment_check.json
```

For teammates running the published image, the helpers need Python 3.12's standard library and Docker. They can use `py -3.12` instead of the development environment executable. GHCR package permissions and authentication are described in the demo guide. Training reproduction additionally requires the local processed traversal CSV and training/test dependencies.

Before presenting, check:

- [ ] The verification command exits successfully and its report says `overall_passed: true`.
- [ ] [Swagger UI](http://127.0.0.1:8001/docs) opens on the demo PC.
- [ ] `GET /health` reports `ready`, model version `1`, and `cold_start_v1`.
- [ ] `POST /predict/bus` returns approximately 6.3204 minutes for the documented sample.
- [ ] An unsupported route such as `999` receives HTTP 422.
- [ ] The Docker container is healthy and its image digest matches `deploy/model-v1.json`.
- [ ] The source commit being shown has a successful Phase 2 CI run.
- [ ] The v1 image-release run shows both publication and verification of the published digest.

Use this prediction request:

```json
{
  "segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB",
  "route_id": "90",
  "entry_at": "2019-07-08T17:10:00+05:30"
}
```

## 3. Present the required MLOps workflow

| Order | Show | Explain |
|---|---|---|
| 1 | Pytest result and representative model/API tests | Automated tests check features, date splits, validation, artifact handling and deployment recovery |
| 2 | Quality report and model comparison | Validation selects the candidate; historical test and route-level errors, positive predictions and checksum checks determine approval |
| 3 | MLflow experiment and `BusTravelTimePredictor` version 1 | Metrics, training run, signature and artifact identity connect evaluation to a versioned model |
| 4 | FastAPI `/health` and `/predict/bus` | The service loads the checked model and returns a versioned duration response |
| 5 | Docker Desktop and the running service | The image packages the model with its inference dependencies and runs through Docker's WSL 2 Linux backend |
| 6 | Successful GitHub Actions CI and release runs | CI runs tests and a synthetic fixture image; the release workflow separately tests and publishes the approved real model |
| 7 | Local deployment command and verification report | The script pulls the immutable published image, starts the local service and checks its behavior |

For the registry demonstration, open the original SQLite store as described in the demo guide. Reproduction runs use independent SQLite stores; version numbers must be interpreted together with their registry URI, run ID and artifact hash.

State the automation boundary clearly: **GitHub Actions automates CI and image release. A local command initiates deployment on the Windows PC.** The implementation does not automatically deploy GitHub commits to the workstation. Recovery has automated test coverage; describe a live rollback only if you have separately performed and recorded one.

## 4. Team review and merge

- [ ] Review the pull request's changed files, passing checks and demonstration evidence.
- [ ] Confirm the PR adds the remaining deployment/approval work without deleting existing project files.
- [ ] Confirm the historical Route 90 scope and local-deployment boundary match the project objectives and assigned tools.
- [ ] The repository owner or authorized teammate reviews and merges the PR into `main`.
- [ ] After merging, teammates update their `main` checkout and follow the deployment commands above.

The approved model is distributed in the released container image. Generated local data and model artifacts remain under their existing ignored directories.
