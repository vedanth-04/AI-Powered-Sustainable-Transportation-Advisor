# Dataset Access, Provenance, and Empirical Schema Audit Report

**Project:** AI-Powered Sustainable Transportation Advisor  
**Phase:** Phase 2 — Dataset Acquisition & Empirical Schema Audit  
**Date:** October 2026  
**Status:** **Completed & Empirically Verified** on representative daily database `2019-07-01.db`  

---

## 1. Executive Summary

This report establishes the data provenance, legal access conditions, storage architecture, and empirical data schema for the Delhi bus GPS dataset.

To conduct Phase 2 safely without consuming multi-gigabytes of local storage or committing large binaries to Git, we inspected the Zenodo deposit (DOI: `10.5281/zenodo.21738157`) and developed a selective byte-range extractor (`src/data/download_sample.py`). This retrieved and decompressed only the first daily database (`2019-07-01.db`) using HTTP Range requests.

The audit notebook (`notebooks/01_dataset_schema_and_integrity_audit.ipynb`) was then executed in the project's `.venv` against the real database. All 1,977,922 observations were audited across completeness, coordinate envelopes, timezone offsets, and duplicates.

### Key Measured Takeaways (Empirical Evidence)
1. **Source & Lineage:** Originates from the **Delhi Open Transit Data (OTD)** initiative, Department of Transport, Government of NCT of Delhi, in association with IIIT-Delhi.
2. **Database Scale (July 1, 2019):** Exactly **1,977,922 records** covering **1,547 unique buses** and **476 transit routes**.
3. **Completeness:** 0 missing values across all 9 schema columns in the July 1 dataset.
4. **Spatial Confinement:** Latitude ranges from **28.490431°N to 28.858192°N**; longitude ranges from **76.841896°E to 77.341705°E**. 100% of observations fall cleanly within the Delhi transit operational envelope.
5. **Collection Clock Latency:** Telemetry epoch (`timestamp`, UTC) converts accurately to IST (+19,800s), but displays an 8–10 second transmission lag relative to server ingestion time (`date`, `time`).
6. **Telemetry Duplication:** **73,034 duplicate `(vehicle_id, timestamp)` pairs** (3.69%) were detected, confirming the necessity of trajectory deduplication before feature engineering.
7. **No Ready-Made Travel Time Labels:** No segment travel-time target exists in the raw schema. Target labels must be mathematically derived from boundary line transits in Phase 3.

---

## 2. Dataset Access Conditions & Legal Usage Terms

A critical tenet of MLOps is compliance with data licensing and ethical usage constraints. We do not assume open redistribution merely because files are hosted on Zenodo.

### 2.1 Provenance & Deposit Attribution
- **Depositor:** Kshitij Srivastava (IIIT-Delhi)
- **Publication Date:** 2026-08-01 (DOI: [10.5281/zenodo.21738157](https://doi.org/10.5281/zenodo.21738157))
- **Associated Academic Research:** *Partial Road Rationing as a Transition Policy: Bus-Speed Evidence, Microsimulation, and Retention Thresholds from Delhi*
- **Software Repository:** [opendata-iiitd/partial-road-rationing-delhi](https://github.com/opendata-iiitd/partial-road-rationing-delhi)

### 2.2 Terms of Use & Licensing Constraints
According to the deposit documentation and Delhi OTD portal terms (`https://otd.delhi.gov.in/terms`):
1. **Non-Relicensing:** The Zenodo deposit **does not relicense** the source records; use and redistribution remain strictly subject to the Delhi Open Transit Data terms.
2. **Source Acknowledgment:** Any publication, model deliverable, or presentation must prominently acknowledge **Delhi Open Transit Data, Department of Transport, Govt. of NCT of Delhi**, and **IIIT-Delhi**.
3. **Privacy & Individual Tracking Prohibitions:** The terms explicitly prohibit any use that enables tracking, identification, or profiling of individuals. The databases contain public bus vehicle IDs and spatial points, but **no passenger identifiers, rider logs, or fare transaction data**.
4. **Academic & Research Scope:** Our project use case (academic evaluation and sustainable transport journey planning) conforms directly with non-commercial academic research declarations.

---

## 3. Selective Acquisition & Verification Architecture

Instead of downloading the entire 1.8 GB compressed archive (`july_19_corrected.zip`), we analyzed the ZIP Central Directory structure remotely using HTTP byte-range requests.

### 3.1 Remote ZIP Stream Architecture
- **Total Archive Size:** 1,817,382,484 bytes (~1.69 GiB)
- **Central Directory Offset:** Byte 1,817,378,987 (length 3,475 bytes)
- **Member Extracted:** `july_19_corrected/2019-07-01.db`
- **Compressed Byte Range:** 1,689,923,027 to 1,751,834,149 (61,911,123 bytes / ~59.04 MB)
- **Compression Method:** Method 8 (Standard Deflate)
- **Decompression Method:** Streaming raw deflate decompressor (`zlib.decompressobj(-zlib.MAX_WBITS)`)

### 3.2 Integrity Validation
- **Computed CRC32:** `0xdd4201c1` (Exact match with Central Directory header)
- **Uncompressed Size:** 193,421,312 bytes (~184.46 MB)
- **SQLite Verification:** `PRAGMA integrity_check` returned `ok`.
- **Location:** `data/raw/2019-07-01.db` (safely ignored by Git).

---

## 4. Empirical Schema & Column Analysis

The database contains a single table: `vehicle_feed`:

```sql
CREATE TABLE vehicle_feed (
  vehicle_id text,
  lat text,
  lng text,
  speed real,
  route_id real,
  trip_id text,
  timestamp text,
  date date,
  time text
);
```

### Empirical Column Metrics (Measured from `2019-07-01.db`)

| Column | Stored Type | Missing Count | Missing % | Sample Values | Validation Notes & Casting Rules |
|---|---|---|---|---|---|
| `vehicle_id` | `TEXT` | 0 | 0.0% | `DL1PD2284`, `DL1PC5853` | 1,547 unique vehicle IDs. Grouping key for trajectories. |
| `lat` | `TEXT` | 0 | 0.0% | `28.6396675109863` | Min: 28.490431, Max: 28.858192. Must cast to `REAL`. |
| `lng` | `TEXT` | 0 | 0.0% | `77.2462997436523` | Min: 76.841896, Max: 77.341705. Must cast to `REAL`. |
| `speed` | `REAL` | 0 | 0.0% | `1.944444`, `0.0`, `2.777778` | Instantaneous GPS speed. 0.0 when parked or at red signal. |
| `route_id` | `REAL` | 0 | 0.0% | `45.0`, `2.0`, `482.0` | 476 unique routes. Stored as float; cast to string integer (`"45"`). |
| `trip_id` | `TEXT` | 0 | 0.0% | `1669`, `137`, `14809` | Scheduled trip identifier from Delhi transit timetable. |
| `timestamp` | `TEXT` | 0 | 0.0% | `1561939202` | UTC Unix epoch in seconds. Ground-truth monotonic clock. |
| `date` | `DATE` | 0 | 0.0% | `2019-07-01` | Service date in India Standard Time (IST, UTC+05:30). |
| `time` | `TEXT` | 0 | 0.0% | `05:30:10` | Ingestion timestamp recorded in IST (HH:MM:SS). |

---

## 5. Temporal Alignment & Timezone Audit

### The 19,800-Second Relationship
India Standard Time (IST) is strictly fixed at UTC+05:30 ($19,800\text{ seconds}$).

- For observation 0:
  - `timestamp` = `1561939202`
  - Converted UTC: `2019-07-01 00:00:02+00:00`
  - Converted IST: `2019-07-01 05:30:02+05:30`
  - Recorded IST (`date` + `time`): `2019-07-01 05:30:10`
- **Observed Update Lag:** The 8-second discrepancy between the onboard GPS timestamp (`05:30:02`) and the central transit server time (`05:30:10`) illustrates real-world GSM transmission buffering. Downstream feature engineering must rely on `timestamp` (the onboard physical clock) rather than the server collection clock.

---

## 6. Data Quality Pitfalls & Invalidation Criteria

From the empirical audit, four key quality issues were measured:

1. **Duplicate Pings:** **73,034 duplicate `(vehicle_id, timestamp)` pairs** were detected (3.69% of records). These occur when telemetry devices retransmit identical packets over noisy GSM links.  
   *Remediation:* Drop duplicate `(vehicle_id, timestamp)` records before sorting trajectories.
2. **Floating-point Route IDs:** `route_id` values like `45.0` cause dictionary lookup failures if matched against integer route codes.  
   *Remediation:* Normalize `route_id` by casting float $\to$ int $\to$ string (`str(int(float(x)))`).
3. **Coordinate Storage Type:** Coordinates stored as text require explicit casting: `CAST(lat AS REAL)`, `CAST(lng AS REAL)`.
4. **The Consecutive Ping Trap:** An elapsed time between successive pings is **not** a travel time. A bus stuck at a signal or depot may log successive pings 15 minutes apart with zero spatial displacement. True segment travel times will be derived exclusively via boundary line crossing events in Phase 3.

---

## 7. Version Control & Proposed DVC Architecture

### Current Status
- `.gitignore` actively prevents `data/raw/2019-07-01.db` from leaking into Git.
- `dvc` (version 3.67.1) is installed in `.venv`.
- DVC has **not** been initialized yet (`.dvc/` does not exist).

### Proposed DVC Setup for Review
When approved, DVC will be initialized and configured as follows:

```powershell
# 1. Initialize DVC in the repository
dvc init

# 2. Track the sample raw database
dvc add data/raw/2019-07-01.db
```

#### Implications of DVC Tracking:
- DVC calculates a content hash (md5) of `2019-07-01.db` and copies it into `.dvc/cache/`.
- DVC automatically creates a 1 KB pointer file: `data/raw/2019-07-01.db.dvc`.
- DVC automatically adds `data/raw/2019-07-01.db` to `data/raw/.gitignore`.
- Git tracks only `data/raw/2019-07-01.db.dvc`, keeping the GitHub repository ultra-lightweight while guaranteeing versioned reproducibility.

---

## 8. Summary of Completed Deliverables

- [x] Verified dataset provenance, terms of use, and citations.
- [x] Selective byte-range extraction of `2019-07-01.db` (~59 MB downloaded vs. 1.8 GB full archive).
- [x] Verified SQLite integrity and extracted 1,977,922 observations.
- [x] Created and executed `notebooks/01_dataset_schema_and_integrity_audit.ipynb` in `.venv`.
- [x] Documented empirical data findings in `docs/schema_audit_report.md`.
- [x] Safeguarded Git repository from large data commits.
