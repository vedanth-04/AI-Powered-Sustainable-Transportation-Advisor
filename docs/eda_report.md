# Exploratory data analysis: verified daily sample

Dataset: Delhi bus GPS, `data/raw/2019-07-01.db`, from the [Zenodo archive](https://zenodo.org/records/21738157/files/july_19_corrected.zip?download=1). This overview corrects abbreviated counts/generalizations that conflicted with the original notebook and [fleet-wide audit](reference/eda_audit_report.md). Read-only SQL and hashes were rechecked on November 9, 2026; [sanitized evidence](results/2026-11-09-validation/summary.json).

## 1. Inventory and completeness

| Metric | Verified value |
|---|---:|
| Raw observations | 1,977,922 |
| Distinct vehicle IDs | 1,547 |
| Distinct route IDs | 476 |
| Distinct trip IDs | 5,194 |
| File size | 193,421,312 bytes |
| Missing/null/blank values | 0 in each of all nine columns |
| Duplicate vehicle/timestamp keys | 73,034 |
| Observations after key deduplication | 1,904,888 |

SQLite integrity returned `ok`. Epoch range is `1561939200` through `1562025599`: July 1 00:00:00–23:59:59 UTC, spanning July 1 05:30 to July 2 05:29:59 IST. A daily archive does not prove complete network/service coverage. The former 816-bus/193-route/8,327-trip summary and claim of null trip IDs are superseded by these queries.

## 2. Temporal and data-quality findings

The notebooks investigate sampling intervals, collection-time delay and trajectory traces. The historical fleet audit reports a ten-second median sampling interval, wider fleet-wide gaps than the Route 90 subset, and 22,828 gaps over 300 seconds within a vehicle/trip pair. These detailed interval statistics were not recomputed in the November inventory check.

The approximately 13-second collection delay in the EDA is a Route 90 observation, not a measured universal network delay. Use onboard epoch `timestamp` for crossing time and convert to IST for time features. A gap can reflect waiting, an outage or other causes; the data alone does not establish why it occurred.

Current cleaning deduplicates vehicle/timestamp keys, filters Delhi coordinate bounds, removes implausible displacement speeds over 80 km/h for adjacent pings up to 60 seconds apart, and starts a new continuity subtrip at gaps over 300 seconds. Label extraction has stricter crossing and within-segment gap bounds. [Label report](label_construction_report.md).

## 3. Speed and route coverage

November 9 SQL found 662,614 zero-speed rows (**33.50%**) and 22 distinct reported speed values, with maximum about 5.833333. The prior audit interprets this as m/s (about 21 km/h). This observed quantization/ceiling does not prove a specific device defect or firmware mechanism. Zero reported speed alone is not a reason to discard real bus-stop/signal waiting.

The historical audit found no Route 90 jumps above 100 km/h but seven above 80 km/h; "zero jumps" without a threshold is incorrect. It also reports larger outliers on Route 399. GPS displacement speed is an estimate subject to location error, not automatically true speed. Neither raw speed nor completed-traversal speed is in the current 12 model inputs.

Top raw route groups rechecked on November 9:

| Dataset route ID | Observations | Vehicle IDs | Trip IDs |
|---|---:|---:|---:|
| 90 | 35,446 | 39 | 39 |
| 399 | 33,814 | 37 | 36 |
| 398 | 32,967 | 36 | 36 |
| 83 | 32,565 | 37 | 37 |
| 164 | 20,845 | 28 | 28 |

The original study reports extensive vehicle route switching. That supports continuity checks; it does not establish the cause of each reassignment. The implemented catalog contains ORR and MB Road in both directions. Geographic landmark and timetable mapping still need independent validation before a journey-planning claim.

## 4. What EDA establishes

EDA supports selecting dense candidate corridors and defining quality rules. It does not establish that two million pings are two million independent training labels: the historical July 1 extraction produced only 152 valid gate traversals. The Phase 2 release is separately evaluated on a documented 637-row processed input and serves only the approved historical Route 90 pair.

Full-month totals in the Phase 1 presentation were not reproduced from this daily sample. Preserve [source/usage terms](reference/schema_audit_report.md), [notebooks](../notebooks/01_dataset_schema_and_integrity_audit.ipynb), [fleet audit](reference/eda_audit_report.md) and the [project chronology](summaries/pipeline_overview.md) when explaining what was measured, inherited or remains unverified.
