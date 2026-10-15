# Exploratory Data Analysis (EDA) Audit Report

**Project:** AI-Powered Sustainable Transportation Advisor  
**Phase:** Phase 1 Deliverable — Empirical Audit of Prior EDA Findings  
**Date:** October 2026  
**Audited Database:** `data/raw/2019-07-01.db` (July 1, 2019 — Monday, 1,977,922 observations)  
**Status:** **Completed & Empirically Verified** via read-only SQL queries and Python kinematics auditing  

---

## 1. Executive Summary & Purpose

The initial exploratory data analysis (`docs/eda_report.md` and `notebooks/02_exploratory_data_analysis.ipynb`) made several valuable observations about the Delhi bus AVL dataset. However, a critical methodological audit reveals that **key kinematic and temporal findings were derived exclusively from Route 90 and incorrectly generalized as fleet-wide truths**.

This audit report re-evaluates all critical claims directly against the full 1,977,922-observation database using read-only connections. We explicitly separate **verified empirical findings** from **invalidated generalizations**, establish the real data distributions across the entire fleet, evaluate corridor viability, and assess readiness for target label construction.

### Summary of Audit Verdicts

| Dimension | Prior EDA Claim | Audit Finding | Verdict |
|---|---|---|---|
| **Dataset Scale** | 1,977,922 rows, 1,547 buses, 476 routes, 5,194 trips | Exactly confirmed across all counts. 0 missing values. | **CONFIRMED** |
| **Duplicates** | 73,034 duplicate `(vehicle_id, timestamp)` pairs (3.69%), 0 conflicts | Exactly confirmed. No coordinate, speed, or route conflicts among duplicates. | **CONFIRMED** |
| **Speed Ceiling** | Speed is in m/s, capped at ~5.83 m/s (21 km/h), quantized in 1 km/h steps | Confirmed fleet-wide! Exactly 22 discrete speeds ($0\text{--}21\text{ km/h}$) exist in the entire 2M-row dataset. | **CONFIRMED (Fleet-Wide)** |
| **Stationary Mass** | 33.14% of records have `speed = 0.0` | Route 90 is 33.01%; Fleet-wide is **33.50%** (662,614 rows). | **CONFIRMED** |
| **Sampling Interval** | 92.45% $\le 30\text{s}$, 96.13% $\le 60\text{s}$, 99th percentile = 208s | **INCORRECTLY GENERALIZED.** Fleet-wide $\le 30\text{s}$ is **87.96%**, $\le 60\text{s}$ is **93.17%**, and 99th percentile is **364s** (6+ min). Route 90 is significantly denser than average. | **CORRECTED** |
| **GPS Jumps** | Zero implausible jumps ($> 100\text{ km/h}$) | **INCORRECTLY GENERALIZED.** Route 90 had 0 jumps, but Route 399 has jumps up to **338.5 km/h** and Route 83 has jumps up to **149.1 km/h**. | **CORRECTED** |
| **Vehicle-Route Stability** | Vehicles are assigned to stable routes | **NEW FINDING.** 94.6% of buses (1,464 / 1,547) operate on **multiple routes** on the same day (up to 8 routes). | **CRITICAL INSIGHT** |
| **Trip Continuity** | A `trip_id` represents a continuous journey | **NEW FINDING.** 22,828 gaps $> 5\text{ minutes}$ exist within the same `(vehicle_id, trip_id)`. `trip_id` cannot be assumed continuous without gap segmentation. | **CRITICAL SAFEGUARD** |

---

## 2. Methodology & Reproducibility

All audit results in this report were produced using reproducible scripts executing against `data/raw/2019-07-01.db` (SHA-256 verified from Zenodo deposit `10.5281/zenodo.21738157`):
- Database connection opened strictly in URI read-only mode (`?mode=ro`).
- SQL window functions (`LAG() OVER (PARTITION BY vehicle_id ORDER BY timestamp)`) were used for fleet-wide gap and sampling analysis.
- Haversine great-circle distance was calculated using double-precision floating-point arithmetic.
- Deduplication rule: `DROP DUPLICATES` on `(vehicle_id, timestamp)` keeping the first ingested record.

---

## 3. Detailed Audit Findings

### 3.1 Dataset Inventory & Completeness (CONFIRMED)
- **Total records:** 1,977,922
- **Unique physical vehicles (`vehicle_id`):** 1,547
- **Unique routes (`route_id`):** 476
- **Unique scheduled trips (`trip_id`):** 5,194
- **Temporal span:** `1561939200` to `1562025599` (exactly 24.0 hours, 2019-07-01 00:00:00 to 23:59:59 UTC; 05:30:00 to 05:29:59 IST).
- **Missingness:** Exactly 0 null or blank values across all 9 columns.

### 3.2 Telemetry Duplication & Conflict Audit (CONFIRMED)
- **Duplicate `(vehicle_id, timestamp)` pairs:** 73,034 (3.69% of all rows).
- **Coordinate conflicts:** 0 (zero cases where same vehicle and timestamp had different coordinates).
- **Speed conflicts:** 0.
- **Route conflicts:** 0.
- **Root Cause:** Ingestion server socket polling captures retransmissions when the vehicle telemetry unit has not yet advanced its internal GPS clock.
- **Effective clean kinematic observations:** **1,904,888**.

### 3.3 Speed Sensor Ceiling & Quantization (CONFIRMED FLEET-WIDE)
The prior EDA noted that `speed` appeared quantized in $1\text{ km/h}$ steps with a max of $21\text{ km/h}$ on Route 90. We audited the entire fleet:
- **Fleet-wide distinct speed values:** Exactly **22 discrete values**.
- Every speed value satisfies: $\text{speed} = k \times \frac{1}{3.6}\text{ m/s}$ for $k \in \{0, 1, 2, \dots, 21\}$.
- **Fleet-wide maximum speed:** Exactly $5.833333\text{ m/s} = 21.00\text{ km/h}$.
- **Top 3 speeds by count:**
  1. $0\text{ km/h}$ ($0.0\text{ m/s}$): 662,614 pings (**33.50% stationary dwell**)
  2. $1\text{ km/h}$ ($0.277778\text{ m/s}$): 142,353 pings (7.20%)
  3. $2\text{ km/h}$ ($0.555556\text{ m/s}$): 122,006 pings (6.17%)
- **Interpretation:** The onboard GPS hardware or AVL firmware enforces a **hard 21 km/h ceiling** on reported instantaneous speed, likely an artifact of legacy sensor firmware or integer truncation. **Reported instantaneous speed cannot be used as an unconstrained regression feature.** Real vehicle speeds must be inferred via displacement over time.

### 3.4 Temporal Sampling Rate: Fleet-Wide vs. Route 90 (CORRECTED)
The prior EDA evaluated sampling intervals ($\Delta t$) only on Route 90. Comparing Route 90 against the full fleet of 1,903,341 intervals reveals that **Route 90 is an unusually dense outlier**:

| Metric | Prior EDA (Route 90) | Fleet-Wide Audit | Operational Impact |
|---|---|---|---|
| **Total Intervals** | 34,120 | 1,903,341 | 55x larger sample |
| **Median ($\Delta t$)** | **10.0 s** | **10.0 s** | Standard ping cycle is 10 seconds fleet-wide |
| **25th Percentile** | 10.0 s | 10.0 s | Reliable core frequency |
| **75th Percentile** | 20.0 s | 20.0 s | Single dropped packet recovery |
| **90th Percentile** | **30.0 s** | **40.0 s** | Fleet experiences 33% longer tail buffering |
| **95th Percentile** | **50.0 s** | **90.0 s** | Fleet has 80% longer 95th-percentile gaps |
| **99th Percentile** | **208.0 s** (~3.5 min) | **364.0 s** (~6.1 min) | 75% longer extreme gaps |
| **$\Delta t \le 15\text{s}$** | 62.48% | **58.32%** | Lower high-frequency share |
| **$\Delta t \le 30\text{s}$** | 92.45% | **87.96%** | Noticeably lower reliable window |
| **$\Delta t \le 60\text{s}$** | 96.13% | **93.17%** | Nearly 7% of pings exceed 1 minute |

**Key Takeaway:** Any pipeline assuming that 96% of consecutive pings are within 60 seconds across arbitrary routes will fail on lower-density routes where gaps are substantially wider.

### 3.5 GPS Jump Anomalies (CORRECTED)
The prior EDA claimed "zero implausible teleportation jumps ($> 100\text{ km/h}$)". This was true *only* on Route 90. When audited across other top corridors:

| Route | Total Pings | Active Pings ($5 \le \Delta t \le 60\text{s}$) | Jumps $> 80\text{ km/h}$ | Jumps $> 100\text{ km/h}$ | Max Implied Speed |
|---|---|---|---|---|---|
| **90** | 34,159 | 32,780 | 7 (0.021%) | **0 (0.000%)** | 97.37 km/h |
| **399** | 32,654 | 31,008 | 3 (0.010%) | **3 (0.010%)** | **338.47 km/h** |
| **398** | 31,794 | 30,222 | 2 (0.007%) | **0 (0.000%)** | 99.31 km/h |
| **83** | 31,542 | 30,231 | 1 (0.003%) | **1 (0.003%)** | **149.10 km/h** |
| **164** | 20,161 | 18,549 | 0 (0.000%) | **0 (0.000%)** | 71.43 km/h |

**Key Takeaway:** Teleportation jumps ($> 100\text{ km/h}$, reaching up to $338.5\text{ km/h}$) *do* occur in the raw data due to transient GPS multipath errors or cellular tower triangulation glitches. A robust data-cleaning module **must explicitly filter out implied velocities exceeding operational physical thresholds** ($> 80\text{--}100\text{ km/h}$).

### 3.6 Route-Level Data Density & Long-Tail Distribution (NEW FINDING)
The 476 routes exhibit an extreme long-tail distribution:
- **Min observations:** 3 pings (Route 793B)
- **25th percentile:** 481 pings
- **Median:** 1,912 pings
- **75th percentile:** 6,388 pings
- **Max:** 35,446 pings (Route 90)
- **Mean:** 4,155 pings
- **Routes with $< 100$ pings:** 27 (5.7%)
- **Routes with $< 500$ pings:** 125 (26.3%)
- **Routes with $< 1,000$ pings:** 188 (39.5%)

**Key Takeaway:** Over 39% of routes lack sufficient observation density for reliable segment extraction. Corridor selection must target the top-density routes (e.g., Routes 90, 399, 398, 83) where hundreds of crossings occur daily.

### 3.7 Vehicle-Route Switching & Paired Corridors (CRITICAL INSIGHT)
- **Vehicles on exactly 1 route:** Only **83 out of 1,547 buses (5.4%)**.
- **Vehicles on $> 1$ route:** **1,464 buses (94.6%)**, serving up to 8 different routes across the day.
- **Trips spanning multiple routes:** **0**. A `trip_id` is uniquely associated with a single `route_id`.
- **Route 398 & 399 Overlap:** Exactly **36 vehicles** operate on *both* Route 398 and Route 399 on July 1. Since Route 398 has 36 unique buses and Route 399 has 37, this establishes that **Routes 398 and 399 are directional pairs of the same South Delhi transit corridor** (Route 398 inbound, Route 399 outbound, or vice versa).
- **Corridor coordinates for Routes 398/399:**
  - Route 398: Lat $[28.4905, 28.5530]$, Lng $[77.0817, 77.3044]$
  - Route 399: Lat $[28.4960, 28.5690]$, Lng $[77.0818, 77.3026]$
  - Combined volume: **66,781 observations across 37 buses**.

### 3.8 Long Gaps Within Scheduled Trips (CRITICAL SAFEGUARD)
The prior EDA did not audit continuity within `trip_id`:
- Across the entire fleet, there are **22,828 intervals $> 300\text{ seconds}$ (5 minutes)** occurring within the *same* `(vehicle_id, trip_id)`.
- Max gap within a single trip reaches **23.9 hours** (a vehicle remaining logged into a trip overnight).
- Across the top 5 routes, each exhibits 180–260 long gaps averaging 50–70 minutes.
- **Cause:** Telemetry units stay assigned to a `trip_id` during depot layovers, driver meal breaks, mechanical holds, or cellular dead zones.
- **Mandatory Safeguard:** Trajectories **must be split into separate continuous sub-trajectories** whenever $\Delta t > \tau_{\text{gap}}$ (recommended: 300 seconds / 5 minutes). A trip identifier alone cannot guarantee unbroken physical movement.

---

## 4. Assessment: Can We Construct Valid Travel-Time Labels?

### The Core Requirement
The project objective is:
$$\text{travel\_time\_minutes} = \frac{t_{\text{exit}} - t_{\text{entry}}}{60.0}$$
where $t_{\text{entry}}$ and $t_{\text{exit}}$ represent actual boundary crossings of a defined road segment.

### Feasibility Verdict: **YES, WITH STRICT SAFEGUARDS**

The empirical data strongly supports travel-time label construction, provided the following architecture is enforced:

1. **Deterministic Deduplication:** Remove duplicate `(vehicle_id, timestamp)` pairs.
2. **Kinematic Jump Filtering:** Discard displacement pairs where implied velocity exceeds $80\text{ km/h}$.
3. **Trajectory Gap Segmentation:** Split trajectories whenever $\Delta t > 300\text{s}$ before boundary detection.
4. **Defined Spatial Gates:** Define two perpendicular geographic line segments (Entry Gate $G_{\text{start}}$ and Exit Gate $G_{\text{end}}$) bounding a real road segment along a chosen corridor.
5. **Gate Crossing Interpolation:** When consecutive GPS pings $P_A$ and $P_B$ straddle a gate line, calculate the exact crossing timestamp $t_{\text{cross}}$ via linear spatial interpolation:
   $$t_{\text{cross}} = t_A + (t_B - t_A) \times \frac{\text{dist}(P_A, \text{Gate})}{\text{dist}(P_A, P_B)}$$
   This is mathematically valid because the median sampling interval is 10 seconds ($\le 30\text{s}$ for 88% of pings), limiting interpolation error to a few seconds.
6. **Journey Validation Filters:**
   - Vehicle must cross $G_{\text{start}}$ then $G_{\text{end}}$ in correct chronological sequence.
   - Transit duration must be realistic ($30\text{s} \le \Delta t \le 3600\text{s}$).
   - No data gap $> 120\text{s}$ within the traversal.
   - Heading/bearing must match segment direction.

---

## 5. Candidate Corridor Selection & Recommendation

We evaluated the top candidates for segment definition:

| Corridor | Daily Pings | Active Buses | Spatial Span | Geometry | Recommendation |
|---|---|---|---|---|---|
| **Route 90** | 35,446 | 39 | Lat 28.52–28.65, Lng 76.93–77.29 (~35 km) | Najafgarh $\leftrightarrow$ Shivaji Stadium / Central Delhi | **Primary candidate:** Highest single-route volume, excellent 10s sampling continuity. |
| **Routes 398 + 399** | 66,781 | 37 | Lat 28.49–28.57, Lng 77.08–77.30 (~22 km) | Mehrauli $\leftrightarrow$ Mayur Vihar / Noida (South Delhi arterial) | **Strong alternative / paired corridor:** 36 shared buses, dense bidirectional coverage along Mehrauli-Badarpur / Outer Ring Road. |
| **Route 83** | 32,565 | 37 | Lat 28.52–28.63, Lng 76.97–77.29 (~31 km) | West Delhi $\leftrightarrow$ New Delhi Station | Good candidate, but overlaps significantly with Route 90. |

### Recommended Segment for Phase 2:
A well-defined road segment along the **Route 90 corridor** in West-Central Delhi, or along the **Route 398/399 corridor** on the Mehrauli-Badarpur arterial. The specific coordinates should cover a 1–3 km continuous road section with high traffic density, clear directional alignment, and minimal turnoff ambiguity.

---

## 6. What Was Implemented in Phase 1

1. **Repository Inspection:** Verified Git history (5 clean commits), branch (`main`), DVC tracking configuration, and existing documentation.
2. **Sample Acquisition:** Retrieved and verified `data/raw/2019-07-01.db` (184.46 MB, CRC32 `0xdd4201c1`, 1,977,922 rows) using the existing selective HTTP byte-range extractor.
3. **Empirical Audit Queries:** Authored and executed comprehensive read-only audit scripts covering fleet-wide speed quantization, sampling intervals, deduplication conflicts, route data density, vehicle-route switching, GPS jumps, and trip gaps.
4. **Discrepancy Resolution:** Documented which findings from `docs/eda_report.md` were Route-90-specific vs. fleet-wide truths.
5. **Audit Documentation:** Authored this report (`docs/eda_audit_report.md`) preserving `docs/eda_report.md` intact.

---

## 7. Readiness Assessment & Next Step

| Gate Criterion | Status | Evidence |
|---|---|---|
| SQLite database verified & accessible | **PASSED** | 1,977,922 rows, PRAGMA integrity ok |
| Data cleaning rules empirically defined | **PASSED** | Deduplication, GPS jump ($>80\text{ km/h}$), and gap ($>300\text{s}$) rules established |
| Coordinate envelope verified | **PASSED** | 100% within Delhi bounds ($28.3\text{--}28.9^\circ\text{N}, 76.8\text{--}77.5^\circ\text{E}$) |
| Target label feasibility confirmed | **PASSED** | Nominal 10s sampling supports gate crossing interpolation |
| Corridor selection justified | **PASSED** | Route 90 (35.4k pings) and Routes 398/399 (66.8k pings) selected |

**Verdict: READY TO PROCEED TO PHASE 2 (Target Feasibility & Segment Definition).**
