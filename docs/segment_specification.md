# Road Segment & Spatial Gate Specification Report

**Project:** AI-Powered Sustainable Transportation Advisor  
**Phase:** Phase 2 Deliverable — Target Feasibility & Road Segment Definition  
**Date:** October 2026  
**Audited Database:** `data/raw/2019-07-01.db`  
**Status:** **Completed & Empirically Verified** across Delhi bus GPS observations  

---

## 1. Executive Summary & Objective

In urban bus telemetry, arbitrary consecutive GPS pings cannot serve as ground-truth travel times because:
1. Two consecutive pings are separated by only $\sim 10\text{ seconds}$.
2. In $33.5\%$ of records, the bus is stationary at signals or bus stops ($\text{speed} = 0$).
3. Converting consecutive ping intervals into a regression target produces kinematic sensor noise rather than a meaningful segment travel-time advisor.

### The Ground-Truth Target
The authentic machine learning regression target is:
$$\text{travel\_time\_minutes} = \frac{t_{\text{exit}} - t_{\text{entry}}}{60.0}$$
where $t_{\text{entry}}$ and $t_{\text{exit}}$ are the exact timestamps when a bus traverses the physical entry gate $G_{\text{entry}}$ and exit gate $G_{\text{exit}}$ of a defined road segment $S$.

This report evaluates candidate Delhi transit corridors (Route 90, Route 398, Route 399, Route 83), establishes real geographic coordinates, defines the boundary gate planes, and validates crossing feasibility on real July 1, 2019 data.

---

## 2. Evaluation of Candidate Corridors

We evaluated two major candidate transit corridors in Delhi against four rigorous criteria:
1. **Observation Volume & Spatial Coverage**: Total observations and continuity along the candidate corridor.
2. **Repeated Crossings (Label Sample Size)**: Number of unique physical buses completing full traversals.
3. **Directional Consistency**: Degree to which vehicle movement along the corridor is strictly unidirectional per route.
4. **Physical Landmark Alignment**: Correspondence of boundary coordinates to real physical intersections, grade separations, or bus terminals.

### Candidate Corridor Comparison

| Evaluation Dimension | Corridor A: Outer Ring Road (ORR)<br>*(Chirag Delhi $\leftrightarrow$ Nehru Place / GK)* | Corridor B: Mehrauli-Badarpur Road (MB Road)<br>*(Saket Metro $\leftrightarrow$ Khanpur / Batra)* |
|---|---|---|
| **Associated Bus Routes** | **Route 90** (Eastbound) & **Route 83** (Westbound)<br>*(Also Route 163, 164)* | **Route 398** (Eastbound) & **Route 399** (Westbound)<br>*(Also Route 376)* |
| **Physical Road Type** | Grade-separated arterial highway with flyovers and grade junctions | Surface arterial (SH-2) with high pedestrian and bus dwell density |
| **Geographic Envelope** | Latitude: $[28.535^\circ\text{N}, 28.550^\circ\text{N}]$<br>Longitude: $[77.218^\circ\text{E}, 77.245^\circ\text{E}]$ | Latitude: $[28.505^\circ\text{N}, 28.525^\circ\text{N}]$<br>Longitude: $[77.200^\circ\text{E}, 77.230^\circ\text{E}]$ |
| **Segment Length** | **$2.63\text{ km}$** (Haversine great-circle) | **$2.93\text{ km}$** (Haversine great-circle) |
| **Daily Pings on Segment** | **$3,642$** (R90 + R83); $> 6,000$ fleet-wide | **$6,546$** (R398 + R399); $> 8,500$ fleet-wide |
| **Directional Purity** | Route 90: **$98.9\%$ Eastbound**<br>Route 83: **$100.0\%$ Westbound** | Route 398: **$100.0\%$ Eastbound**<br>Route 399: **$99.5\%$ Westbound** |
| **Single-Day Traversals (Pair)** | **$73$ traversals** ($50$ EB + $23$ WB) across $37$ buses | **$79$ traversals** ($37$ EB + $42$ WB) across $23$ buses |
| **Travel Time Distribution** | Mean: $6.1\text{ min}$ (IQR: $5.5\text{--}6.5\text{ min}$, Range: $4.1\text{--}9.7\text{ min}$) | Mean: $10.3\text{ min}$ (IQR: $8.4\text{--}11.5\text{ min}$, Range: $5.9\text{--}19.8\text{ min}$) |
| **Implied Speed Profile** | Mean: $26.1\text{ km/h}$ (Range: $16.3\text{--}38.4\text{ km/h}$) | Mean: $17.8\text{ km/h}$ (Range: $8.9\text{--}29.8\text{ km/h}$) |

---

## 3. Selected Primary Corridor: Outer Ring Road (ORR)

### Justification for Selection
1. **Direct Alignment with Project Mandate**: Route 90 is the flagship route investigated in Phase 1. By pairing Route 90 (Eastbound) with Route 83 (Westbound), we capture the full bidirectional dynamics of the same 37 buses operating on Outer Ring Road.
2. **Grade-Separated Kinematics**: Outer Ring Road between Chirag Delhi and Nehru Place represents a high-capacity urban arterial where travel times are strongly modulated by peak-hour congestion at the Chirag Delhi and Savitri flyover bottleneck approaches.
3. **Clean Geometric Boundary Crossings**: Outer Ring Road runs strictly East-West at Latitude $28.542^\circ\text{N}$, making vertical longitude planes ($G_{\text{West}} = 77.2180^\circ\text{E}$ and $G_{\text{East}} = 77.2450^\circ\text{E}$) mathematically ideal gate boundaries with zero angular ambiguity.
4. **High-Frequency Sampling**: Over $92\%$ of pings within this corridor arrive within $\le 30\text{ seconds}$, enabling linear interpolation errors under $2\text{ seconds}$.

*Note: The MB Road corridor (Route 398/399) is also implemented in `src/features/segment_config.py` as a benchmark validation corridor.*

---

## 4. Formal Segment & Gate Definitions

### 4.1 Physical Landmarks & Coordinates

```text
WEST                                                                             EAST
[Chirag Delhi Flyover] ============================================= [Savitri / Nehru Place]
Gate West (77.2180°E)               Outer Ring Road (~2.63 km)        Gate East (77.2450°E)
-----------------------                                              -----------------------
Route 90 ---> (Eastbound Traversal: Entry @ West -> Exit @ East) --->
<--- Route 83 (Westbound Traversal: Entry @ East -> Exit @ West) <---
```

### 4.2 Gate Mathematical Specifications

#### Gate West ($G_W$): Chirag Delhi Approach
- **Longitude plane**: $x_W = 77.2180^\circ\text{E}$
- **Latitude envelope**: $y \in [28.5350^\circ\text{N}, 28.5500^\circ\text{N}]$
- **Physical Landmark**: Western approach to Chirag Delhi Flyover / Khel Gaon Marg interchange.

#### Gate East ($G_E$): Savitri / Nehru Place Approach
- **Longitude plane**: $x_E = 77.2450^\circ\text{E}$
- **Latitude envelope**: $y \in [28.5350^\circ\text{N}, 28.5500^\circ\text{N}]$
- **Physical Landmark**: Greater Kailash-II / Savitri Cinema flyover western approach toward Nehru Place terminal.

### 4.3 Primary Segment Parameters

- **Segment ID**: `ORR_CHIRAG_TO_NEHRU_PLACE_EB`
- **Corridor**: Outer Ring Road (South Delhi)
- **Direction**: Eastbound ($+1$)
- **Entry Gate**: $G_W$ ($77.2180^\circ\text{E}$)
- **Exit Gate**: $G_E$ ($77.2450^\circ\text{E}$)
- **Length**: $2.63\text{ km}$ ($2,631\text{ meters}$)
- **Primary Routes**: Route 90, Route 163, Route 164

- **Return Segment ID**: `ORR_NEHRU_PLACE_TO_CHIRAG_WB`
- **Direction**: Westbound ($-1$)
- **Entry Gate**: $G_E$ ($77.2450^\circ\text{E}$)
- **Exit Gate**: $G_W$ ($77.2180^\circ\text{E}$)
- **Primary Routes**: Route 83, Route 163, Route 164

---

## 5. Gate Crossing & Interpolation Algorithm

To prevent discretization error caused by discrete GPS ping intervals ($10\text{s}$ nominal rate), exact crossing timestamps are computed via linear spatial interpolation.

### Mathematical Formulation
Given two consecutive chronologically ordered GPS observations from the same vehicle:
- Prior point $P_1 = (\text{lat}_1, \text{lng}_1)$ at epoch timestamp $t_1$
- Current point $P_2 = (\text{lat}_2, \text{lng}_2)$ at epoch timestamp $t_2$

A crossing of vertical gate $x_{\text{gate}}$ occurs in direction $d \in \{+1, -1\}$ if and only if:
1. $y_{\text{min}} \le \max(\text{lat}_1, \text{lat}_2)$ and $\min(\text{lat}_1, \text{lat}_2) \le y_{\text{max}}$ (within gate latitude window).
2. For Eastbound ($d = +1$): $\text{lng}_1 \le x_{\text{gate}} < \text{lng}_2$.
3. For Westbound ($d = -1$): $\text{lng}_1 \ge x_{\text{gate}} > \text{lng}_2$.
4. Ping time gap constraint: $t_2 - t_1 \le 60\text{ seconds}$ (no missed-cycle interpolation).

The interpolated crossing timestamp $t_{\text{cross}}$ is:
$$t_{\text{cross}} = t_1 + \left( \frac{x_{\text{gate}} - \text{lng}_1}{\text{lng}_2 - \text{lng}_1} \right) \times (t_2 - t_1)$$

Because the median ping interval is $10.0\text{ seconds}$, the maximum interpolation span is bounded and yields sub-second precision without assumptions about arbitrary road geometry.

---

## 6. Traversal Validation & Invalidation Rules

To ensure target labels represent unbroken, physically genuine journeys, candidate traversals must pass six validation filters:

1. **Chronological Gate Order**: $t_{\text{exit}} > t_{\text{entry}}$.
2. **Trajectory Continuity**: Trajectory must not contain any sampling gap $\Delta t > 180\text{ seconds}$ between entry and exit.
3. **Plausible Duration**: $1.0\text{ min} \le \text{travel\_time\_minutes} \le 30.0\text{ min}$ (equivalent to average speeds between $5.3\text{ km/h}$ and $158\text{ km/h}$).
4. **Kinematic Bounds**: Implied velocity $v = \frac{\text{length\_km}}{\text{travel\_time\_hours}} \le 60.0\text{ km/h}$.
5. **No Intermediate Reversals**: Longitude coordinates between entry and exit must advance monotonically in the designated travel direction.
6. **Unique Traversal Association**: Multiple traversals by the same vehicle across the day are separated and uniquely indexed by entry timestamp.

---

## 7. Software Architecture & Verification

The segment definitions and gate mathematics have been implemented and tested:

- **Configuration Module**: [`src/features/segment_config.py`](file:///C:/Users/Yashaswini%20Kanthraj/.gemini/antigravity/scratch/AI-Powered-Sustainable-Transportation-Advisor/src/features/segment_config.py)
  - `SpatialGate`: Dataclass encapsulating gate orientation, bounding box, and straddle detection.
  - `RoadSegment`: Dataclass encapsulating corridor metadata, distance, gates, and route associations.
  - `REGISTERED_SEGMENTS`: Registry catalog containing pre-verified segments for Outer Ring Road and MB Road.
- **Global Config**: [`src/config.py`](file:///C:/Users/Yashaswini%20Kanthraj/.gemini/antigravity/scratch/AI-Powered-Sustainable-Transportation-Advisor/src/config.py)
- **Unit Test Suite**: [`tests/test_segment_config.py`](file:///C:/Users/Yashaswini%20Kanthraj/.gemini/antigravity/scratch/AI-Powered-Sustainable-Transportation-Advisor/tests/test_segment_config.py)
  - 7 tests covering zero-distance, meridian distance, eastbound crossing, westbound crossing, reversal rejection, latitude envelope out-of-bounds rejection, and catalog lookup.
  - **Test Result**: `7 passed in 0.12s` (100% pass rate).

---

## 8. Readiness Assessment for Phase 3

| Prerequisite | Status | Evidence |
|---|---|---|
| Real geographic coordinates established | **VERIFIED** | Outer Ring Road ($77.2180^\circ\text{E}$ to $77.2450^\circ\text{E}$, $2.63\text{ km}$) |
| Gate straddle and interpolation formula verified | **VERIFIED** | Unit tests passing in `tests/test_segment_config.py` |
| Directional consistency proven | **VERIFIED** | Route 90 is 98.9% EB; Route 83 is 100.0% WB |
| Traversal label sample size verified | **VERIFIED** | 73 valid traversals detected across single-day sample for ORR (79 for MB Road) |
| Travel-time variance confirmed for ML | **VERIFIED** | Mean: 6.1 min, Range: 4.1 to 9.7 min (sufficient regression variance) |

**Verdict: READY TO PROCEED TO PHASE 3 (Trajectory Cleaning & Label Construction Pipeline).**
