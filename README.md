# AI-Powered Sustainable Transportation Advisor

An applied MLOps project for predicting urban bus-segment travel times using real-world Delhi bus GPS observations, designed to enable accurate, reliable, and sustainable public transit journey planning.

---

## 1. Problem Statement

Public transit reliability is a major barrier to sustainable urban mobility. In dense metropolitan networks like Delhi, buses experience dynamic congestion, dwell times, and traffic variability. 

This project tackles the core machine-learning task:
- **Core ML Task:** Supervised Regression
- **Prediction Target:** Bus-segment travel time (in minutes)
- **Input Data:** Historical Delhi bus GPS observations, timestamps, vehicle/trip identifiers, and spatial network features
- **Potential Features:** Segment identifier, travel direction, segment distance (km), departure hour of day, day of week, and historical rolling transit statistics
- **Initial Models:**
  1. *Historical-Median Baseline* (heuristic benchmark)
  2. *Random Forest Regressor* (non-linear ensemble baseline)
  3. *Gradient Boosting Regressor* (sequential error-correcting ensemble)
- **Evaluation Metrics:** Mean Absolute Error (MAE), Root Mean Squared Error (RMSE), and stratified route-wise and time-of-day error analysis.

> **CRITICAL DATA MODELING RULE:**  
> The raw dataset does **not** provide ready-made travel-time labels. Arbitrary consecutive GPS pings must **not** be blindly treated as valid segment travel times. True labels must be mathematically derived by verifying vehicle journeys that cleanly cross defined segment start and end boundaries within valid operational thresholds.

---

## 2. Dataset & Quality Specifications

- **Source:** Zenodo Delhi Bus GPS Archive (`july_19_corrected.zip`, ~1.8 GB compressed)
- **Archive URL:** [Zenodo Record 21738157](https://zenodo.org/records/21738157/files/july_19_corrected.zip?download=1)
- **Format:** Daily SQLite databases containing timestamped vehicle locations, routes, and trips.
- **Data Quality & Audit Requirements:**
  - Verify access terms, attribution, and dataset licensing.
  - Audit timestamps, verify UTC/IST time zones, identify clock drift and day-boundary overlaps.
  - Detect and remove duplicate observations and sampling gaps.
  - Filter out stale pings (e.g., parked buses transmitting zero velocity with identical coordinates for hours).
  - Explicitly document and log all rejected records and reasons before downstream feature engineering.
  - Initial exploratory work will be conducted on a representative daily sample before scaling to the full multi-gigabyte archive.

---

## 3. Academic Deliverables & Timeline

- **Milestone Review:** 13–17 October 2026 (Class Hours)
- **Required Deliverables:**
  1. Dataset acquisition, licensing, and usage-terms verification.
  2. Exploratory Data Analysis (EDA) and rigorous data quality audit.
  3. Systematic segment boundary label derivation and feature engineering.
  4. Baseline heuristic and tree-based model training and benchmarking.
  5. Clean, structured Git repository with meaningful team commit history.
  6. **DVC (Data Version Control):** Explicit dataset versioning without storing gigabyte binaries in Git.
  7. **MLflow:** Comprehensive experiment tracking (parameters, metrics, artifacts, model signatures).
  8. Transparent error analysis across different routes and transit hours.
- **Reproducibility Guarantee:** All results, metrics, and models must be backed by verifiable code and artifacts. No fabricated results or placeholder claims.

---

## 4. Technology Stack

| Layer | Tool / Library | Version / Details |
|---|---|---|
| **Language & Environment** | Python | 3.12.5 (Windows PowerShell) |
| **Development** | VS Code & Jupyter | Interactive development and notebooks |
| **Data Manipulation** | pandas, NumPy, SQLite | Vectorized tabular processing and database queries |
| **Visualization** | Matplotlib, Seaborn | Distribution plots and error breakdowns |
| **Machine Learning** | scikit-learn | Tree regressors, baselines, and evaluation metrics |
| **Data Version Control** | DVC | Dataset tracking and pipeline reproducibility |
| **Experiment Tracking** | MLflow | Run logging, metric comparison, model registry |
| **Version Control** | Git & GitHub | Collaborative branch-based development |

---

## 5. Repository Structure

```text
ML-OPS-EL/
├── .gitignore               <- Excludes .venv/, caches, model binaries, mlruns/, and raw datasets
├── CONTRIBUTING.md          <- Comprehensive team setup, Git workflow, and troubleshooting guide
├── README.md                <- Project overview, problem statement, and architecture (this file)
├── requirements.txt         <- Pinned Python dependencies
├── data/
│   ├── README.md            <- Data lifecycle and pipeline documentation
│   ├── raw/                 <- Original SQLite archives (tracked by DVC, ignored by Git)
│   ├── interim/             <- Cleaned, validated, and deduplicated intermediate tables
│   └── processed/           <- Modeling-ready datasets with derived segment travel times
├── docs/
│   └── README.md            <- Research notes, schema reports, and milestone deliverable logs
├── notebooks/
│   └── README.md            <- Numbered Jupyter notebooks for EDA and prototyping
├── outputs/                 <- Evaluation charts, error distribution plots, and summary metrics
├── src/
│   ├── __init__.py          <- Package definition
│   └── README.md            <- Architecture plan for production data, features, and model modules
└── tests/
    ├── __init__.py          <- Test suite initialization
    └── README.md            <- Unit test instructions and test cases
```

---

## 6. Quick Start for Team Members

For detailed step-by-step setup on Windows, Git commands, DVC instructions, and MLflow tracking, please read the [CONTRIBUTING.md](CONTRIBUTING.md) guide.

```powershell
# 1. Clone repository (once remote is published)
git clone <repository-url>
cd ML-OPS-EL

# 2. Activate virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# 3. Verify packages
pip list

# 4. Run tests
pytest
```

---

## 7. Reproducible Pipeline & Execution Guide

All phases from raw SQLite ingestion to model evaluation and MLflow registration can be reproduced using modular CLI commands:

### Step 1: Download / Verify Sample Database
```powershell
python src/data/download_sample.py
```
*Retrieves and verifies the July 1, 2019 SQLite database (`data/raw/2019-07-01.db`, 184.46 MB) from Zenodo.*

### Step 2: Clean Trajectories & Construct Target Labels
```powershell
python -m src.features.build_labels
```
*Applies deduplication, GPS jump filtering (>80 km/h), trajectory gap segmentation (>300s), and sub-second gate crossing interpolation. Generates `data/processed/traversals.csv` (152 ground-truth traversals).*

### Step 3: Build Leakage-Safe Features
```powershell
python -c "import pandas as pd; from src.features.build_features import engineer_features; df = pd.read_csv('data/processed/traversals.csv'); engineer_features(df).to_csv('data/processed/features.csv', index=False)"
```
*Constructs cyclical time encodings, operational rush-hour categories, and strictly causal rolling historical congestion aggregates.*

### Step 4: Train Models, Evaluate & Register with MLflow
```powershell
python -m src.models.train
```
*Executes a chronological 75/25 train-test split, trains the Historical-Median Baseline, Random Forest Regressor, and Gradient Boosting Regressor, logs runs to MLflow experiment `BusTravelTime-ModelSelection`, and registers the winning model as `BusTravelTimePredictor`.*

### Step 5: Run Full Automated Test Suite
```powershell
pytest tests/ -v
```
*Executes all 25 unit tests across data cleaning, spatial gates, label extraction, feature leakage safeguards, and model pipelines.*

### Step 6: Launch MLflow UI Dashboard
```powershell
mlflow ui
```
*Open [http://127.0.0.1:5000](http://127.0.0.1:5000) to inspect run parameters, metric curves, artifacts, and registered models.*

---

## 8. Benchmark Evaluation Results

Corrected retraining is complete: Random Forest MAE **1.87 minutes**, Gradient Boosting **1.94 minutes**, baseline **2.44 minutes**. See [measured feature importance and corrected results](docs/results/2026-10-16-corrected/README.md). The historical table below is superseded.

> These historical scores predate the removal of a target-derived speed feature and must be reevaluated. Retrain with the corrected feature list before interpreting model accuracy. Training also generates per-model feature-importance CSVs and plots; see `docs/feature_engineering_report.md`.

All models evaluated on the unseen chronological test set (38 traversals):

| Model | Test MAE (min) | Test RMSE (min) | Test MAPE (%) | Test $R^2$ | Status |
|---|---|---|---|---|---|
| **Gradient Boosting Regressor** | **0.62 min** (37 sec) | **1.38 min** | **5.28%** | **0.850** | **Selected & Registered** |
| **Random Forest Regressor** | **0.75 min** (45 sec) | **1.54 min** | **6.52%** | **0.812** | Benchmark Ensemble |
| **Historical-Median Baseline** | **2.44 min** | **3.39 min** | **22.96%** | **0.089** | Heuristic Benchmark |

## 9. Phase 2 Local Inference Demo

Run this from the repository root in the Python 3.12 release environment. The exporter uses the passing quality report and numbered local registry version recorded in `outputs/phase2_release_check`. It verifies the approved joblib artifact and writes the local serving bundle under `outputs/phase2_serving`.

```powershell
.\.venv\Scripts\python.exe -m src.models.export_serving_bundle
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Open [Swagger UI](http://127.0.0.1:8000/docs) and try `POST /predict/bus`.

```json
{
  "segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB",
  "route_id": "90",
  "entry_at": "2019-07-08T17:10:00+05:30"
}
```

The prediction returns segment riding time in minutes, the model version, and the cold-start policy. `GET /health` reports readiness. Invalid requests and routes outside the approved historical demo receive HTTP 422. An unavailable or invalid bundle returns HTTP 503.

## 10. Phase 2 Docker Demo

Start Docker Desktop in Linux container mode. From the repository root, export the approved model bundle, build the image, and run it on localhost.

```powershell
.\.venv\Scripts\python.exe -m src.models.export_serving_bundle
docker build --tag bus-travel-time:phase2-v1 .
docker run --rm --name bus-travel-time-demo --publish 127.0.0.1:8000:8000 bus-travel-time:phase2-v1
```

The build includes the two verified bundle files under `outputs/phase2_serving`. A fresh checkout needs this bundle before building. The running container uses the bundled artifact and verifies its checksum at startup.

In another PowerShell terminal, run `Invoke-RestMethod http://127.0.0.1:8000/health` and check for `ready` and model version `1`. Open [Swagger UI](http://127.0.0.1:8000/docs) and submit the Route 90 request from section 9. Version 1 should return approximately **6.32 minutes**. Use Ctrl+C in the container terminal to stop the demo.

## 11. Phase 2 Continuous Integration

The **Phase 2 CI** workflow runs on pull requests and pushes to `main` or `phase2/model-quality`. In the repository's **Actions** tab, open the run for your commit and check the Pytest, Docker build, and HTTP smoke-test steps.

The runner creates a synthetic Route 90 model bundle in its fresh checkout. The Docker smoke test checks readiness, a fixture prediction of **6.25 minutes**, and HTTP 422 for an unsupported route. The 6.32-minute result in section 10 comes from the approved model. CI uses the fixture to check the build and API contract without needing access to the local registry or GPS data.

## 12. Phase 2 Model v1 Image Release

Push the Phase 2 source commit and wait for CI to pass on it. Export the approved bundle as in section 9. With GitHub CLI authenticated for the repository and permission to set Actions secrets, upload the verified bundle before pushing the release tag on that commit.

```powershell
.\.venv\Scripts\python.exe -m scripts.release_bundle upload --repo vedanth-04/AI-Powered-Sustainable-Transportation-Advisor
git tag phase2-image-v1
git push origin refs/tags/phase2-image-v1
```

The upload stores only the approved model and manifest in the versioned Actions secrets `PHASE2_MODEL_V1_PART_1` and `PHASE2_MODEL_V1_PART_2`. The tagged workflow checks both file hashes before building and checks the approved Route 90 prediction before pushing `ghcr.io/vedanth-04/ai-powered-sustainable-transportation-advisor/bus-travel-time:v1`.

A fresh runner pulls the published image by digest and repeats the HTTP smoke test. Use the digest from the successful **Phase 2 Model v1 Release** run summary as the deployment reference.

## 13. Phase 2 Deployment on Windows with WSL 2

Start Docker Desktop's Linux engine and run the deployment from PowerShell in the repository root. Authenticate Docker to GHCR first if the package requires pull access.

```powershell
docker login ghcr.io
.\.venv\Scripts\python.exe -m scripts.deploy_api --port 8001
```

The deployment uses the image digest in `deploy/model-v1.json`. It pulls the image, starts a dedicated Docker Compose service, waits for readiness, and checks the model version, Route 90 prediction, and rejection of an unsupported route. The active and prior release records are stored in `outputs/phase2_deploy/state.json`. A failed update restores the prior release and reports the failure.

Open [Swagger UI on port 8001](http://127.0.0.1:8001/docs) and try the request from section 9. For the demo, show the successful GitHub release run and the same image responding on the Windows host. GitHub Actions automates CI and image publication. The command above starts the workstation deployment, with the port published to localhost.

