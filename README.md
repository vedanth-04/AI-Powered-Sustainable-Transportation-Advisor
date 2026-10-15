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
