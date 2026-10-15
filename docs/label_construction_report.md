# Trajectory Cleaning & Label Construction Report

**Project:** AI-Powered Sustainable Transportation Advisor  
**Phase:** Phase 3 Deliverable — Trajectory Cleaning & Target Label Construction  
**Date:** October 2026  
**Audited Database:** `data/raw/2019-07-01.db`  
**Generated Dataset:** `data/processed/traversals.csv` (152 ground-truth traversals)  
**Status:** **Completed & Verified** with 16 automated unit tests passing  

---

## 1. Executive Summary

Phase 3 implements the core data processing and travel-time label generation pipeline. 

Raw GPS pings from the Delhi bus AVL system are intermittent kinematic points ($\Delta t \approx 10\text{s}$). Arbitrary successive pings cannot be treated as segment travel times. This pipeline extracts ground-truth segment travel times by detecting verified physical vehicle traversals across spatial boundary gates defined in Phase 2.

### Pipeline Execution Summary

```text
[Raw SQLite Data] 
       │
       ▼
1. Trajectory Cleaning (src/data/cleaner.py)
   ├── Type normalization (lat, lng, speed, timestamp)
   ├── Spatial envelope filtering (Delhi bounds [28.3, 28.9]°N, [76.8, 77.5]°E)
   ├── Deterministic deduplication on (vehicle_id, timestamp)
   ├── Kinematic jump filtering (implied speed > 80 km/h)
   └── Trajectory gap segmentation (Δt > 300s triggers new subtrip_id)
       │
       ▼
2. Gate Crossing Detection & Interpolation (src/features/label_generation.py)
   ├── Entry gate straddle detection (direction-constrained)
   ├── Linear crossing timestamp interpolation (sub-second precision)
   ├── Exit gate straddle detection (strictly after entry)
   ├── Internal continuity check (no intra-traversal gap > 180s)
   └── Duration bounds validation (1.0 min ≤ duration ≤ 30.0 min, avg speed ≤ 70 km/h)
       │
       ▼
[data/processed/traversals.csv]
   └── 152 verified traversals across 57 unique physical buses
```

---

## 2. Empirical Ingestion & Cleaning Metrics

The pipeline processed all candidate corridor observations from `data/raw/2019-07-01.db`:

| Corridor & Segment | Raw Observations | Duplicates Dropped | GPS Jumps Removed | Subtrips Generated | Unique Buses |
|---|---|---|---|---|---|
| **ORR Eastbound** (`ORR_CHIRAG_TO_NEHRU_PLACE_EB`) | 5,849 | 233 | 2 | 306 | 64 |
| **ORR Westbound** (`ORR_NEHRU_PLACE_TO_CHIRAG_WB`) | 5,711 | 172 | 0 | 295 | 63 |
| **MB Road Eastbound** (`MB_SAKET_TO_KHANPUR_EB`) | 6,156 | 173 | 2 | 210 | 54 |
| **MB Road Westbound** (`MB_KHANPUR_TO_SAKET_WB`) | 6,069 | 211 | 1 | 190 | 55 |
| **Total** | **23,785** | **789** | **5** | **1,001** | **57 (Distinct Fleet)** |

---

## 3. Traversal Extraction & Rejection Audit

To prevent false or contaminated traversals from entering model training, candidate journeys were strictly audited against gate crossing constraints:

| Segment ID | Entry Crossings | Exit Crossings | Rejected (No Exit) | Rejected (Gap $>180\text{s}$) | Valid Traversals Generated |
|---|---|---|---|---|---|
| `ORR_CHIRAG_TO_NEHRU_PLACE_EB` | 84 | 58 | 26 | 8 | **50** |
| `ORR_NEHRU_PLACE_TO_CHIRAG_WB` | 77 | 24 | 53 | 1 | **23** |
| `MB_SAKET_TO_KHANPUR_EB` | 83 | 51 | 32 | 14 | **37** |
| `MB_KHANPUR_TO_SAKET_WB` | 83 | 46 | 37 | 4 | **42** |
| **Total** | **327** | **179** | **148** | **27** | **152** |

### Explanations for Rejections:
1. **Rejected (No Exit)** ($148$ instances): A bus passed the entry gate but turned off the corridor before reaching the exit gate, terminated its trip, or took a depot layover. These incomplete journeys are safely discarded with zero target contamination.
2. **Rejected (Gap $> 180\text{s}$)** ($27$ instances): A bus traversed the segment but experienced a cellular outage or extended stop $> 3\text{ minutes}$. These are dropped to avoid distorting the continuous moving travel time.

---

## 4. Ground-Truth Target Label Characteristics

The generated dataset is saved at `data/processed/traversals.csv` with 16 columns:
- Identification: `segment_id`, `corridor_name`, `direction`, `vehicle_id`, `route_id`.
- Provenance & Crossings: `t_entry`, `t_exit`, `entry_time_ist`, `exit_time_ist`, `entry_hour`, `entry_minute`, `date`.
- Regression Target: `travel_time_minutes` ($= \frac{t_{\text{exit}} - t_{\text{entry}}}{60.0}$).
- Physical Validation: `segment_length_km`, `avg_speed_kmh`, `num_pings`.

### Traversal Summary Statistics

| Segment ID | Direction | Count | Mean Duration (min) | Std (min) | Min (min) | Median (min) | Max (min) | Mean Speed (km/h) |
|---|---|---|---|---|---|---|---|---|
| `ORR_CHIRAG_TO_NEHRU_PLACE_EB` | EASTBOUND | 50 | 6.25 | 1.17 | 4.12 | 5.91 | 9.74 | 26.06 |
| `ORR_NEHRU_PLACE_TO_CHIRAG_WB` | WESTBOUND | 23 | 5.82 | 0.68 | 4.35 | 5.84 | 7.57 | 27.54 |
| `MB_SAKET_TO_KHANPUR_EB` | EASTBOUND | 37 | 10.49 | 2.89 | 5.90 | 9.79 | 19.85 | 17.84 |
| `MB_KHANPUR_TO_SAKET_WB` | WESTBOUND | 42 | 10.13 | 1.85 | 6.19 | 10.31 | 13.68 | 18.03 |
| **All Combined** | — | **152** | **8.29** | **2.76** | **4.12** | **6.75** | **19.85** | **22.09** |

---

## 5. Software Quality & Unit Test Suite

Phase 3 is backed by 16 passing unit tests across 3 dedicated test modules:

```text
tests/test_label_generation.py::test_gate_crossing_interpolation_precision PASSED
tests/test_label_generation.py::test_extract_segment_traversals_valid_journey PASSED
tests/test_label_generation.py::test_extract_segment_traversals_gap_rejection PASSED
tests/test_label_generation.py::test_extract_segment_traversals_duration_out_of_bounds PASSED
tests/test_segment_config.py::test_haversine_zero_distance PASSED
tests/test_segment_config.py::test_haversine_known_meridian_distance PASSED
tests/test_segment_config.py::test_spatial_gate_clean_eastbound_crossing PASSED
tests/test_segment_config.py::test_spatial_gate_clean_westbound_crossing PASSED
tests/test_segment_config.py::test_spatial_gate_wrong_direction_rejected PASSED
tests/test_segment_config.py::test_spatial_gate_out_of_bounds_latitude_rejected PASSED
tests/test_segment_config.py::test_registered_segments_catalog PASSED
tests/test_trajectory_cleaning.py::test_clean_trajectory_empty PASSED
tests/test_trajectory_cleaning.py::test_clean_trajectory_deduplication PASSED
tests/test_trajectory_cleaning.py::test_clean_trajectory_out_of_bounds PASSED
tests/test_trajectory_cleaning.py::test_clean_trajectory_gps_jump_filtered PASSED
tests/test_trajectory_cleaning.py::test_clean_trajectory_gap_segmentation PASSED

16 passed in 0.96s
```

---

## 6. Readiness for Phase 4 (Feature Engineering)

With 152 verified, unbroken segment traversals and ground-truth travel times derived, the project is ready for **Phase 4 (Feature Engineering)**.

Features to be built (at the prediction moment $t_{\text{entry}}$):
1. **Temporal & Schedule Features**: `entry_hour`, `minute_of_day`, `is_morning_rush` (08:00–11:00), `is_evening_rush` (17:00–20:00), `is_midday` (11:00–16:00).
2. **Spatial & Network Features**: `segment_id`, `direction`, `segment_length_km`, `route_id`.
3. **Approach Kinematics**: Implied speed in the approach buffer before entering the gate ($v_{\text{approach}}$).
4. **Leakage-Safe Historical Aggregates**: Rolling historical median travel time computed **strictly from past traversals** ($t_{\text{exit}} \le t_{\text{entry}}$).
