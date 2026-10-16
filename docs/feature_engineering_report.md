# Feature Engineering & Leakage Prevention Specification Report

> **Correction:** `approach_speed_kmh` has been removed from model inputs. The previous implementation copied completed-traversal `avg_speed_kmh`, which is calculated from the target, rather than measuring pre-entry speed. There are now 12 model inputs (4 categorical, 8 numeric). Old generated datasets may retain this column, but the training pipeline explicitly selects only the current input list. Rebuild features and retrain existing models. Earlier verification claims below do not validate the removed speed feature.

### Feature importance

Training now saves `<model>_feature_importance.csv` and `.png` in `outputs/` and logs them to MLflow for each model. These use 20 seeded permutations per original input column on the chronological test set, scoring the increase in MAE in minutes. A larger positive increase means greater model reliance. Zero/negative importance means no demonstrated improvement in this evaluation; correlated features can mask each other. Shuffle standard deviations are not confidence intervals. These diagnostics do not prove causality or justify selecting features using the same test set. Use separate chronological validation folds for feature selection. No new rankings or corrected model scores are claimed until real-data retraining is completed.


**Project:** AI-Powered Sustainable Transportation Advisor  
**Phase:** Phase 4 Deliverable — Feature Engineering & Leakage Safeguards  
**Date:** October 2026  
**Generated Dataset:** `data/processed/features.csv` (152 rows, 24 columns)  
**Status:** **Completed & Verified** with 21 automated unit tests passing  

---

## 1. Executive Summary & The Prediction Moment

In operational urban transit prediction, machine learning models frequently suffer from subtle data leakage where information from the future (or the target itself) is inadvertently leaked into input features during training.

### The Strict Prediction Moment Rule
For any bus $i$ traversing road segment $S$, **the prediction moment is defined strictly as $t_{\text{entry}, i}$** — the exact instant the vehicle crosses the entry gate line.

```text
PAST (< t_entry)                        PREDICTION MOMENT (t_entry)            FUTURE (> t_entry)
───────────────────────────────────────┼───────────────────────────────────────┼──────────────────────►
• Historical completed traversals      │ • Model predicts:                     │ • Traversal progression
  where t_exit(j) ≤ t_entry(i)         │   travel_time_minutes                 │ • Internal signals/dwell
• Vehicle entry hour & minute of day   │                                       │ • Exit gate crossing: t_exit
• Route, segment, & corridor length    │   (Target is strictly in the future)  │ • Ground-truth travel time
• Pre-entry approach speed             │                                       │   (STRICTLY LEAK-PROTECTED)
```

**Leakage Protection Invariant:**
No feature may incorporate observations, coordinates, speeds, or event timestamps that occur at or after $t_{\text{entry}, i}$. Any earlier traversal $j$ is eligible for inclusion in historical aggregates if and only if:
$$t_{\text{exit}, j} \le t_{\text{entry}, i}$$

---

## 2. Feature Schema & Engineering Specifications

### Table 1: Feature Catalog

| Feature Name | Category | Type | Unit | Description & Derivation |
|---|---|---|---|---|
| `segment_id` | Spatial | `str` (Cat) | Categorical | Identifier of the physical road segment (e.g., `ORR_CHIRAG_TO_NEHRU_PLACE_EB`). |
| `corridor_name` | Spatial | `str` (Cat) | Categorical | High-level transit corridor (Outer Ring Road vs. Mehrauli-Badarpur Road). |
| `direction` | Spatial | `str` (Cat) | Categorical | Direction of travel (`EASTBOUND` vs. `WESTBOUND`). |
| `route_id` | Network | `str` (Cat) | Categorical | Bus route number (e.g., `'90'`, `'83'`, `'398'`, `'399'`). |
| `segment_length_km`| Spatial | `float` | Kilometers | Great-circle Haversine distance between entry and exit gates ($2.63\text{ km}$ on ORR, $2.93\text{ km}$ on MB Road). |
| `entry_hour` | Temporal | `int` | Hour ($0\text{--}23$) | Service hour in India Standard Time (IST). |
| `minute_of_day` | Temporal | `float` | Minutes ($0\text{--}1440$) | Continuous time-of-day: $\text{entry\_hour} \times 60 + \text{entry\_minute}$. |
| `sin_time` | Temporal | `float` | Unitless ($[-1, 1]$) | Cyclical time component: $\sin\left(\frac{2\pi \cdot \text{minute\_of\_day}}{1440}\right)$. Continuous across midnight. |
| `cos_time` | Temporal | `float` | Unitless ($[-1, 1]$) | Cyclical time component: $\cos\left(\frac{2\pi \cdot \text{minute\_of\_day}}{1440}\right)$. Continuous across midnight. |
| `rush_hour_cat` | Temporal | `str` (Cat) | Categorical | Operational traffic period: `MORNING_RUSH` (08:00–11:00), `MIDDAY` (11:00–17:00), `EVENING_RUSH` (17:00–21:00), `OFF_PEAK` (all other times). |
| `hist_segment_median_tt`| Historical | `float` | Minutes | Rolling median travel time of all traversals on this segment completed prior to $t_{\text{entry}}$. Falls back to nominal duration if cold. |
| `hist_recent_60m_mean_tt`| Historical | `float` | Minutes | Rolling mean travel time of traversals on this segment completed in the preceding 60 minutes ($t_{\text{entry}} - 3600 \le t_{\text{exit}} \le t_{\text{entry}}$). Captures dynamic traffic surges. |
| `hist_completed_count` | Historical | `int` | Count | Number of prior traversals completed on this segment in memory. |
| **`travel_time_minutes`** | **TARGET** | `float` | Minutes | **Supervised target**: $(t_{\text{exit}} - t_{\text{entry}}) / 60.0$. Kept strictly out of feature matrix $X$. |

---

## 3. Causal Historical Features & Anti-Leakage Algorithm

The causal historical feature generator operates in $O(N \log N + N \cdot K)$ time using an entry-ordered sweep line:

```python
# Causal conditioning condition:
completed_mask = (t_exits[:i] <= curr_t_entry) & (segment_ids[:i] == curr_seg)
```

### Cold-Start Policy
When a bus enters a segment early in the morning and zero previous buses have exited on that segment:
1. `hist_completed_count` is set to $0$.
2. `hist_segment_median_tt` and `hist_recent_60m_mean_tt` fall back to the nominal physical travel time:
   $$\text{nominal\_fallback\_minutes} = \frac{\text{segment\_length\_km}}{v_{\text{nominal}}} \times 60.0$$
   where $v_{\text{nominal}} = 22.0\text{ km/h}$ (the empirical fleet-wide moving average bus speed).

### Concurrent Overlap Protection
If Bus A enters at 08:15 and exits at 08:23, and Bus B enters at 08:19:
- At 08:19 (Bus B's prediction moment), Bus A has not yet exited ($08:23 > 08:19$).
- Therefore, Bus A's travel time is strictly excluded from Bus B's historical features.
- This was empirically validated via unit test `test_no_concurrent_overlap_leakage` in `tests/test_feature_engineering.py`.

---

## 4. Categorical Encoding & Unseen Route Policy

### Handling of Unseen Routes in Production
In real-world deployment, transit agencies frequently re-route buses or introduce feeder lines. Our pipeline handles unseen categorical values gracefully:
1. **Scikit-Learn OneHotEncoder** is configured with `handle_unknown="ignore"`:
   - When an unfamiliar `route_id` appears at inference time, all one-hot columns for route are zeroed out.
   - The model relies on the strong spatial features (`segment_id`, `direction`, `segment_length_km`), temporal features (`minute_of_day`, `rush_hour_cat`), and historical traffic state (`hist_recent_60m_mean_tt`) to produce robust predictions.
2. **Missing Value Imputation**:
   - Numeric features have zero nulls by design (guaranteed by deterministic fallbacks).
   - `SimpleImputer(strategy="median")` is chained in the pipeline as an operational safeguard.

---

## 5. Verification & Unit Testing

The feature engineering module [`src/features/build_features.py`](file:///C:/Users/Yashaswini%20Kanthraj/.gemini/antigravity/scratch/AI-Powered-Sustainable-Transportation-Advisor/src/features/build_features.py) is verified with 5 unit tests in [`tests/test_feature_engineering.py`](file:///C:/Users/Yashaswini%20Kanthraj/.gemini/antigravity/scratch/AI-Powered-Sustainable-Transportation-Advisor/tests/test_feature_engineering.py):

```text
tests/test_feature_engineering.py::test_rush_hour_categories PASSED
tests/test_feature_engineering.py::test_cyclical_time_encoding_bounds PASSED
tests/test_feature_engineering.py::test_no_future_data_leakage PASSED
tests/test_feature_engineering.py::test_no_concurrent_overlap_leakage PASSED
tests/test_feature_engineering.py::test_feature_columns_schema_complete PASSED
```

**Full Test Suite Status:** **21 passed in 3.93s** (100% pass rate).

---

## 6. Readiness for Phase 5 (Baseline and ML Model Training)

The feature table `data/processed/features.csv` is fully generated, validated, and ready for model benchmarking:
1. **Benchmark Baseline**: Historical-Median Regressor.
2. **Ensemble Baseline**: Random Forest Regressor.
3. **Sequential Ensemble**: Gradient Boosting Regressor.
4. **Evaluation**: Chronological train/test split (preventing time-leakage).
