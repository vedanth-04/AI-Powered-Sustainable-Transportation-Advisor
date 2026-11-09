# EDA summary: the verified July 1 sample

The SQLite sample contains **1,977,922 observations, 1,547 buses, 476 route IDs and 5,194 trip IDs**. Read-only SQL reconfirmed these on November 9, 2026; the [validation record](../results/2026-11-09-validation/summary.json) records the query and database hash.

The original notebooks investigated schema, missingness, duplicate messages, coordinates, Route 90 sampling/delay, speed disagreement and route traces. The [fleet-wide audit](../reference/eda_audit_report.md) reports 73,034 duplicate keys and 33.50% zero-speed observations. Zero speed alone does not establish a bad record: buses can wait at signals or stops.

The observed speed field has 22 values up to about 5.833333 m/s (21 km/h). That is an observed data limit; a hardware/firmware cause is not established. Displacement-based speed is also susceptible to GPS errors. The current model uses neither raw nor completed-traversal speed as an input.

Typical sampling is about ten seconds, but Route 90 results must not be generalized to every route. Long gaps and changing route assignments motivate deduplication, spatial checks and continuity segmentation before label extraction. See the [corrected EDA overview](../eda_report.md).

The full-month inventory stated in the Phase 1 presentation was not reproduced here; only the local daily sample was checked. EDA supports an experiment design, not a claim of present-day model accuracy.
