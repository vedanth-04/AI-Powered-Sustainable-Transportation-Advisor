# Data Directory Architecture

This directory organizes data across its lifecycle for the **AI-Powered Sustainable Transportation Advisor** project.

## Directory Structure

```text
data/
├── README.md        <- This documentation file
├── raw/             <- Immutable original SQLite archives / daily databases
├── interim/         <- Cleaned, validated, and filtered intermediate datasets
└── processed/       <- Feature-engineered datasets with derived segment travel-time labels ready for modeling
```

## Data Lifecycle & Rules

1. **`raw/` (Immutable Raw Data)**
   - **Source:** Zenodo Delhi Bus GPS Archive (`july_19_corrected.zip`, ~1.8 GB).
   - Contains daily SQLite databases.
   - **Rule:** Never edit, format, or overwrite files in `raw/`. These are the ground-truth inputs for all downstream pipelines.
   - **Version Control:** Raw archives must NOT be checked into Git. They will be tracked and versioned using DVC (Data Version Control).

2. **`interim/` (Validated & Filtered Data)**
   - Contains datasets after initial quality audits, schema standardization, and noise filtering:
     - Deduplication of observation timestamps.
     - Filtering out unrealistic GPS coordinates (outside Delhi transit bounding box).
     - Removal of stale/parked vehicle pings (speed = 0 for extended periods or identical repeated coordinates).
     - Sampling gap handling and day-boundary resolution.
   - All dropped records and rejection reasons must be logged during this phase.

3. **`processed/` (Modeling-Ready Data)**
   - Contains feature tables and derived target labels:
     - **Target:** Bus-segment travel time in minutes.
     - **Important:** Arbitrary consecutive GPS timestamps must *not* automatically be treated as valid segment travel times. Labels are derived specifically from verified vehicle journeys crossing defined segment start and end boundaries.
     - Ready for ingestion into baseline and ML models.

## Dataset Acquisition Reference

- **Zenodo Archive URL:** [https://zenodo.org/records/21738157/files/july_19_corrected.zip?download=1](https://zenodo.org/records/21738157/files/july_19_corrected.zip?download=1)
- Refer to `docs/` and project `README.md` for terms of use, licensing, and sample extraction instructions.
