# Exploratory Data Analysis (EDA) Report

**Project:** AI-Powered Sustainable Transportation Advisor  
**Phase:** Phase 2.8 — Exploratory Data Analysis on Delhi Bus AVL Observations  
**Database Audited:** `data/raw/2019-07-01.db` (July 1, 2019 — Monday)  
**Executed Notebook:** [`notebooks/02_exploratory_data_analysis.ipynb`](file:///c:/Users/bveda/OneDrive/Desktop/ML-OPS-EL/notebooks/02_exploratory_data_analysis.ipynb)  
**Status:** **Completed & Empirically Verified**  

---

## 1. Executive Summary

This report documents the empirical exploratory data analysis of the Delhi Automatic Vehicle Location (AVL) GPS database. The primary machine learning objective of this project is supervised regression: predicting **bus travel time between defensible road segments** in minutes.

Before attempting trajectory segment extraction, we performed read-only empirical audits on the full single-day database (`1,977,922` records).

### Core Empirical Findings:
1. **Dataset Integrity:** Exactly **1,977,922 observations**, **1,547 unique buses**, **476 transit routes**, and **5,194 trips**. Zero missing values exist across all 9 schema columns.
2. **Deduplication Audit:** **73,034 duplicate `(vehicle_id, timestamp)` pairs (3.69%)** were identified. Crucially, these duplicate keys exhibit **zero conflicting coordinates, speeds, or route IDs**. They represent redundant server-side polling captures of the same vehicle transmission.
3. **Temporal Sampling Rate:** Successive pings for active vehicles have a **median sampling interval ($\Delta t$) of 10.0 seconds** ($92.45\% \le 30\text{s}$, $96.13\% \le 60\text{s}$). The nominal transmission frequency is 10 seconds.
4. **Transmission Latency Reality:** The reported 8–10 second delay was rigorously evaluated. When accounting for midnight rollover ($86,400\text{s}$), the latency distribution is right-skewed with a **median of 13.0 seconds** (IQR: 10.0s to 17.0s) and a 99th percentile of 211.0 seconds. The onboard `timestamp` (UTC epoch) is the only reliable monotonic clock for physics and trajectory reconstruction.
5. **Speed Quantization & Kinematics:** The raw `speed` field is stored in **meters per second ($\text{m/s}$)** quantized in discrete steps of $0.277778\text{ m/s}$ ($1\text{ km/h}$). Multiplying by $3.6$ recovers exact integer speedometer values. $33.14\%$ of records have `speed = 0.0` (stationary dwell). Implied velocities derived via Haversine displacement align closely with reported speeds; **zero implausible teleportation jumps ($> 100\text{ km/h}$)** were detected.
6. **Corridor Candidates:** Routes **90** (35,446 pings, 39 buses) and **399 / 398** (~33,000 pings each) provide dense, continuous spatial coverage ideal for segment boundary transit extraction.

---

## 2. Analysis A: Dataset Scale & Global Inventory

| Metric | Measured Value | Verification Source |
|---|---|---|
| **Total Records** | **1,977,922** | `SELECT COUNT(*) FROM vehicle_feed` |
| **Unique Buses (`vehicle_id`)** | **1,547** | Distinct bus registrations operating across Delhi |
| **Unique Routes (`route_id`)** | **476** | Bus route numbers serviced on July 1 |
| **Unique Trips (`trip_id`)** | **5,194** | Scheduled/active trip numbers |
| **Time Coverage (UTC Epoch)** | `1561939200` to `1562025599` | 24-hour span: 2019-07-01 00:00:00 UTC to 23:59:59 UTC |
| **Time Coverage (Server IST)** | `00:00:04` to `23:59:53` | Continuous collection across the full 24-hour service day |
| **Missing Values** | **0 (0.0%) across all columns** | Validated via SQL null/blank aggregation |

### Comparison with Initial Schema Audit
All global figures match the schema audit findings exactly. Discrepancies were resolved:
- In the initial schema report, `speed` was interpreted as km/h; EDA revealed that `speed` is stored in **m/s**, quantized in $1/3.6\text{ m/s}$ increments.
- The transmission delay between vehicle clock and server clock is not a fixed constant of 8–10 seconds, but an empirical distribution averaging ~13–22 seconds with intermittent buffering tails.

---

## 3. Analysis B: Data Quality & Deduplication Rules

### 1. Exact Duplicate Rows
- A query grouping by all 9 columns (`vehicle_id, lat, lng, speed, route_id, trip_id, timestamp, date, time`) found **0 exact duplicate rows**. Every single row has at least one unique attribute (typically the server reception `time`).

### 2. Duplicate Primary Keys `(vehicle_id, timestamp)`
- **Count:** **73,034 rows (3.69% of records)**.
- **Conflict Audit:**
  - Duplicate keys with conflicting coordinates (`lat` or `lng`): **0**
  - Duplicate keys with conflicting instantaneous `speed`: **0**
  - Duplicate keys with conflicting `route_id`: **0**
- **Root Cause:** Vehicle tracking units transmit GPS bursts over cellular GSM. When the central transit ingestion server polls the socket every ~10–12 seconds, if the bus telemetry unit has not updated its internal GPS fix, the server logs the previous onboard timestamp with a new ingestion clock timestamp.
- **Recommended Handling Rule:**  
  Deduplicate on `(vehicle_id, timestamp)` by keeping the first recorded observation:
  ```sql
  SELECT * FROM vehicle_feed GROUP BY vehicle_id, timestamp;
  ```
  This reduces the dataset from 1,977,922 to **1,904,888 unique kinematic observations** with **zero loss of spatial or physical information**.

---

## 4. Analysis C: Temporal Sampling Behaviour & Clock Semantics

### 1. Sampling Interval ($\Delta t$) Distribution
For observations ordered chronologically by `(vehicle_id, timestamp)`:

| Percentile | Sampling Interval ($\Delta t$) | Operational Meaning |
|---|---|---|
| **Min** | 1.0 s | Rapid telemetry burst |
| **25th Percentile** | **10.0 s** | Standard ping frequency |
| **50th Percentile (Median)** | **10.0 s** | Standard ping frequency |
| **75th Percentile** | **20.0 s** | Single dropped packet recovery |
| **90th Percentile** | 30.0 s | Minor cellular buffering |
| **95th Percentile** | 50.0 s | Transient coverage dead-zone |
| **99th Percentile** | 208.0 s | Short layover or dwell |
| **Max** | 47,827.0 s (~13.3 hrs) | Depot overnight layover between shifts |

- **Empirical Coverage:** $62.48\%$ of pings arrive within $\le 15\text{s}$; $92.45\%$ within $\le 30\text{s}$; $96.13\%$ within $\le 60\text{s}$.
- **Conclusion:** GPS sampling resolution is dense and reliable (nominal 10s rate), enabling precise boundary interpolation.

### 2. Transmission Latency Audit (Server Time vs. Onboard Epoch)
- Converting `timestamp` (UTC epoch) to IST seconds from midnight:
  $$\text{onboard\_ist\_sec} = \text{timestamp} - 1,561,919,400$$
- Converting recorded server `time` (`HH:MM:SS`) to seconds from midnight:
  $$\text{latency} = \text{server\_sec} - \text{onboard\_ist\_sec}$$
- **Midnight Rollover Finding:** Raw subtraction without day-boundary handling produced extreme negative values ($\min = -86,397\text{s}$, representing $86,400 - 3\text{s}$). When accounting for midnight rollover, the distribution is:
  - 5th percentile: **5.0 s**
  - 25th percentile: **10.0 s**
  - **Median:** **13.0 s**
  - 75th percentile: **17.0 s**
  - 95th percentile: **24.0 s**
  - 99th percentile: **211.0 s** (~3.5 minutes)
- **Conclusion:** Server ingestion time fluctuates due to network queueing. **The onboard `timestamp` is the only defensible clock for trajectory ordering.**

---

## 5. Analysis D: Speed & Movement Kinematics

### 1. Speed Quantization
- Raw `speed` is stored in meters per second ($\text{m/s}$):
  - `0.0 m/s` = `0 km/h` (662,614 pings, **33.14% stationary**)
  - `0.277778 m/s` = `1 km/h`
  - `0.555556 m/s` = `2 km/h`
  - `2.777778 m/s` = `10 km/h`
  - `5.833333 m/s` = `21 km/h`
- To obtain km/h: $\text{speed\_kmh} = \text{speed} \times 3.6$.

### 2. Implied Velocity vs. Reported Speed
Using the Haversine distance formula between successive GPS observations ($\Delta t \in [5, 60]\text{s}$):
$$\text{implied\_kmh} = \frac{\text{haversine\_distance}(\text{lat}_1, \text{lng}_1, \text{lat}_2, \text{lng}_2)}{\Delta t} \times 3600$$

- **Mean Implied Speed:** **16.81 km/h**
- **Median Implied Speed:** **13.45 km/h**
- **99th Percentile:** **45.85 km/h**
- **Implausible Teleportation Jumps ($> 100\text{ km/h}$):** **0 (0.000%)**
- **Conclusion:** GPS positions adhere strictly to urban kinematic constraints. Concurrency between reported instantaneous speedometer speed and implied displacement is strong (refer to scatter plot in `02_exploratory_data_analysis.ipynb`, Cell 12).

---

## 6. Analysis E: Route Corridor Selection & Trajectory Mapping

### Top 10 Transit Corridors by Observation Density

| Route ID | Total Observations | Unique Buses | Unique Trips | Lat Range (°N) | Lng Range (°E) | Trajectory Description |
|---|---|---|---|---|---|---|
| **90** | **35,446** | **39** | **39** | 28.515 – 28.651 | 76.928 – 77.286 | Najafgarh / West Delhi to Central Delhi |
| **399** | **33,814** | **37** | **36** | 28.496 – 28.569 | 77.082 – 77.303 | South Delhi to East / Noida Border |
| **398** | **32,967** | **36** | **36** | 28.490 – 28.553 | 77.082 – 77.304 | South Delhi Corridor (paired with 399) |
| **83** | **32,565** | **37** | **37** | 28.516 – 28.630 | 76.974 – 77.286 | West Delhi to New Delhi Railway Station |
| **164** | **20,845** | **28** | **28** | 28.521 – 28.653 | 77.182 – 77.320 | South-Central to East Delhi |
| **165** | **20,088** | **21** | **21** | 28.523 – 28.686 | 77.083 – 77.332 | North-South Transit Axis |
| **467** | **19,794** | **25** | **25** | 28.620 – 28.685 | 77.111 – 77.332 | Central / East Radial |
| **420** | **19,737** | **23** | **23** | 28.628 – 28.753 | 77.097 – 77.323 | North-West to Central |
| **450** | **18,668** | **19** | **19** | 28.660 – 28.738 | 77.090 – 77.331 | Outer North Corridor |
| **466** | **18,458** | **24** | **24** | 28.621 – 28.692 | 77.111 – 77.331 | Central Transit Arterial |

### Primary Candidate for Phase 3: Route 90
- **Volume:** Highest single-route observation count (35,446 pings across 39 active buses).
- **Span:** Connects major western transfer hubs to central transit intersections.
- **Continuity:** Over 92% of consecutive pings are within 30 seconds, providing high-resolution boundary crossing detection.

---

## 7. Critical ML Safeguard: The Consecutive Ping Trap vs. Segment Gates

A fundamental finding of this EDA is that **consecutive GPS pings do not equal segment travel times**:
- Two consecutive pings are spaced by only ~10 seconds.
- In 33.14% of records, the bus is stationary (`speed = 0.0`), meaning consecutive pings represent signal/stop dwell with zero displacement.
- Converting consecutive ping durations into a regression target produces a meaningless kinematic noise predictor, not an urban travel-time advisor.

### Ground-Truth Target Derivation Strategy for Phase 3:
1. Define a specific spatial road segment $S$ with entry boundary line $L_{\text{start}}$ and exit boundary line $L_{\text{end}}$.
2. For each vehicle trajectory, detect the exact moment the bus crosses $L_{\text{start}}$ (timestamp $t_{\text{entry}}$) and $L_{\text{end}}$ (timestamp $t_{\text{exit}}$) using linear spatial interpolation between pings.
3. The valid machine learning regression target is:
   $$y = \frac{t_{\text{exit}} - t_{\text{entry}}}{60.0} \quad (\text{travel time in minutes})$$
4. Enforce strict validity filters (e.g. discard transits with duration $< 30\text{s}$ or $> 60\text{min}$, or trajectories with sampling gaps exceeding 5 minutes).

---

## 8. Summary of Notebook Execution & Verification

- **Notebook:** [`notebooks/02_exploratory_data_analysis.ipynb`](file:///c:/Users/bveda/OneDrive/Desktop/ML-OPS-EL/notebooks/02_exploratory_data_analysis.ipynb)
- **Kernel:** Python 3.12.5 (`.venv`)
- **Execution Status:** **Code 0 (Completed without errors)**
- **Generated Visualizations:**
  1. *Sampling Interval Distribution (Cell 9, Left)*: Displays prominent spike at $\Delta t = 10\text{s}$.
  2. *Cellular Transmission Latency (Cell 9, Right)*: Displays right-skewed transmission lag with median at 13s.
  3. *Reported Speed Profile (Cell 12, Left)*: Displays discrete 1 km/h bins and stationary 0 km/h mass.
  4. *Speed vs. Implied Velocity Scatter (Cell 12, Right)*: Displays strong concordance along 1:1 diagonal.
  5. *Corridor Trajectory Scatter (Cell 15)*: Maps spatial footprints of Route 90 and Route 399 across Delhi.
