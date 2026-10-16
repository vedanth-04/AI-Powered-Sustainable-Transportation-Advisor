# Model Training, Benchmarking, and Evaluation Report

> **Superseded benchmark:** The scores and model-selection claims below were produced before removing the target-derived `approach_speed_kmh` feature. They are retained as historical records, not validated performance of the corrected pipeline. Regenerate features and rerun `python -m src.models.train` to obtain corrected metrics and per-model permutation-importance CSVs/plots. Corrected results are now available in [the measured-results report](results/2026-10-16-corrected/README.md): Random Forest MAE 1.8694 minutes, Gradient Boosting 1.9427 minutes, baseline 2.4412 minutes.

**Project:** AI-Powered Sustainable Transportation Advisor  
**Phase:** Phase 5 & 6 Deliverable — Model Training, Evaluation, and MLflow Integration  
**Date:** October 2026  
**Experiment Name:** `BusTravelTime-ModelSelection`  
**Registered Model Name:** `BusTravelTimePredictor` (Version 1)  
**Winning Model:** Gradient Boosting Regressor ($\text{MAE} = 0.62\text{ min}$, $R^2 = 0.850$)  
**Status:** **Completed & Verified** with MLflow experiment tracking and model registration  

---

## 1. Executive Summary

This report documents the machine learning modeling phase for urban bus segment travel-time prediction. Using 152 ground-truth traversals derived across four Delhi road segments on July 1, 2019, we trained and compared three model families:
1. **Historical-Median Baseline** (Heuristic benchmark)
2. **Random Forest Regressor** (Non-linear bagging ensemble)
3. **Gradient Boosting Regressor** (Sequential error-correcting gradient boosting)

All models were evaluated using a strictly **chronological train/test split** (earlier 75% train, later 25% test), ensuring models predict future traversals from past observations without time-travel leakage.

---

## 2. Evaluation Strategy & Anti-Leakage Split

In public transit operations, random K-Fold cross-validation leaks future traffic congestion into past predictions. We enforce a strictly **chronological split**:

```text
TIMELINE (July 1, 2019)
05:30 IST ───────────────────────────────────────────────► 16:30 IST ─────────────────────────► 22:00 IST
│◄───────────── CHRONOLOGICAL TRAIN (75%, 114 samples) ─────────────►│◄──── TEST (25%, 38 samples) ────►│
```

- **Training Set**: First 114 traversals ($t_{\text{entry}} \le 1561978200$)
- **Test Set**: Final 38 traversals ($t_{\text{entry}} > 1561978200$)
- **Guaranteed Condition**: $\min(t_{\text{entry, test}}) \ge \max(t_{\text{entry, train}})$. Zero future information leaked into model parameters or historical aggregates.

---

## 3. Model Benchmark Comparison

All metrics are evaluated on the unseen chronological test set (38 traversals):

| Model Name | Test MAE (min) | Test RMSE (min) | Test MAPE (%) | Test $R^2$ | Train MAE (min) | Train RMSE (min) | Overfit Gap |
|---|---|---|---|---|---|---|---|
| **Gradient Boosting Regressor** *(WINNER)* | **0.62** | **1.38** | **5.28%** | **0.850** | 0.02 | 0.02 | Low |
| **Random Forest Regressor** | **0.75** | **1.54** | **6.52%** | **0.812** | 0.05 | 0.11 | Low |
| **Historical-Median Baseline** | **2.44** | **3.39** | **22.96%** | **0.089** | 0.90 | 1.28 | Benchmark |

### Key Benchmark Findings:
1. **Ensemble Superiority**: Gradient Boosting achieves a **$74.7\%$ error reduction** relative to the Historical-Median Baseline (MAE drops from $2.44\text{ min}$ to $0.62\text{ min}$).
2. **Sub-Minute Precision**: The Gradient Boosting model predicts travel time with an average error of **37 seconds** across $2.6\text{--}2.9\text{ km}$ urban road segments.
3. **High Variance Explained**: The model explains **$85.0\%$ of travel-time variance** ($R^2 = 0.850$) on the unseen test set, demonstrating that combining spatial attributes, cyclical time of day, and causal rolling traffic features effectively captures congestion dynamics.

---

## 4. Stratified Error Breakdowns (Best Model: Gradient Boosting)

To ensure the model is equitable across operational slices and does not conceal large corridor-specific failures, we stratified test errors across segments, directions, and time periods:

### 4.1 Error Breakdown by Segment

| Segment ID | Direction | Length | Test Samples | MAE (min) | RMSE (min) | MAPE (%) |
|---|---|---|---|---|---|---|
| `ORR_CHIRAG_TO_NEHRU_PLACE_EB` | EASTBOUND | 2.63 km | 10 | **0.52** | 0.65 | 6.94% |
| `ORR_NEHRU_PLACE_TO_CHIRAG_WB` | WESTBOUND | 2.63 km | 8 | **0.19** | 0.28 | 3.34% |
| `MB_SAKET_TO_KHANPUR_EB` | EASTBOUND | 2.93 km | 15 | **1.08** | 2.11 | 6.60% |
| `MB_KHANPUR_TO_SAKET_WB` | WESTBOUND | 2.93 km | 5 | **0.12** | 0.12 | 1.09% |

**Insight**: Westbound segments exhibit exceptionally low errors ($\text{MAE} < 0.2\text{ min}$), reflecting smoother flow along the reverse-peak directions in the late afternoon. Eastbound MB Road shows higher variance ($\text{MAE} = 1.08\text{ min}$), driven by the notorious Khanpur T-point surface congestion during evening rush hours.

### 4.2 Error Breakdown by Direction

| Direction | Test Samples | MAE (min) | RMSE (min) | MAPE (%) |
|---|---|---|---|---|
| **EASTBOUND** | 25 | 0.86 min | 1.69 min | 6.74% |
| **WESTBOUND** | 13 | 0.16 min | 0.23 min | 2.48% |

### 4.3 Error Breakdown by Operational Period

| Operational Period | Test Samples | MAE (min) | RMSE (min) | MAPE (%) |
|---|---|---|---|---|
| **EVENING_RUSH** (17:00 – 21:00) | 24 | **0.48 min** | 0.92 min | 4.27% |
| **OFF_PEAK** (Late Evening / Night) | 14 | **0.85 min** | 1.92 min | 7.01% |

**Insight**: The model maintains high accuracy during the dense evening peak ($\text{MAE} = 0.48\text{ min}$ / 29 seconds), benefiting from abundant recent rolling observations.

---

## 5. MLOps & MLflow Integration

Experiment tracking and model registration were conducted in compliance with the MLOps architecture:

- **MLflow Tracking Server**: Local SQLite / file store (`mlruns/`).
- **Experiment Name**: `BusTravelTime-ModelSelection`
- **Logged Runs**:
  1. `Historical-Median Baseline`
  2. `Random Forest Regressor`
  3. `Gradient Boosting Regressor`
  4. `SelectedBest-Gradient Boosting Regressor`
- **Logged Parameters**:
  - `model_name`, `n_estimators`, `max_depth`, `learning_rate`, `train_samples`, `test_samples`, `split_strategy="chronological_75_25"`, `random_seed=42`.
- **Logged Metrics**:
  - `test_mae_minutes`, `test_rmse_minutes`, `test_mape_percent`, `test_r2_score`, `train_mae_minutes`, `train_rmse_minutes`.
- **Logged Artifacts**:
  - Model binary pipeline (`gradient_boosting_regressor.joblib`).
  - Actual vs. Predicted scatter plot (`actual_vs_predicted.png`).
  - Error distribution residual KDE plot (`error_distributions.png`).
- **Model Registry**:
  - Winning model registered under the planned name: **`BusTravelTimePredictor` (Version 1)**.

---

## 6. Limitations & Honest MLOps Disclosures

1. **Single-Day Sample (July 1, 2019)**:
   All observations originate from a single Monday. While the model demonstrates strong within-day chronological generalization ($R^2 = 0.850$), **we make no claim that this single-day model generalizes to weekends, rainy seasons, or different months without multi-day retraining**.
2. **Sample Size ($N = 152$)**:
   The 152 traversals represent only vehicles that cleanly completed continuous gate-to-gate crossings. As more daily databases are pulled from the 1.8 GB Zenodo archive via DVC, the training dataset can be scaled to thousands of traversals.
3. **Hardware Speed Ceiling Artifact**:
   As discovered in Phase 1, raw vehicle speed is capped at $21\text{ km/h}$ in the source feed. The ML models avoid using raw speed as a feature, using the current explicit feature list; completed-traversal speeds are excluded.
