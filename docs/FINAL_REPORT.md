# Final report: AI-Powered Sustainable Transportation Advisor (Delhi)

*21 November 2026 · repository `vedanth-04/AI-Powered-Sustainable-Transportation-Advisor`*

This is the single end-of-project report. It covers what was built, the research question and its observed answer, the evaluation, ten demo cases, the model versions (including the advisor release as version 4) and the limitations. Detailed method documents are linked where they exist; this report does not repeat them.

## 1. Summary

We trained a regression model that predicts how long a Delhi bus takes to cross a verified road segment, from GPS traversals recorded in July 2019. We deployed it behind a narrow, governed API and put it under MLOps control: drift monitoring, versioning with a promotion gate, rollback, a hash-chained audit log, an MLflow registry mirror and a dashboard. On top of it we built a multimodal journey advisor for Delhi. It combines DTC/cluster buses, the Delhi Metro, local passenger trains, cabs and auto-rickshaws from public Delhi data. It ranks options by fare within a budget, time, changes, walking and CO₂, and explains each recommendation.

**Answer to the research question, as observed.** On the one corridor where the advisor uses the model (Outer Ring Road, Chirag Delhi → Nehru Place, eastbound), the model's error on the held-out day was 1.03 min. The historical median's was 1.27 min, and the constant-speed timetable's was 4.09 min. The model also cut late arrivals of more than 5 minutes from 5.6% (median) to 0%. Across all four segments the model beats the median on held-out data: 3.39 vs 4.18 min for v2, and 3.62 vs 4.27 min for v1. The evidence is narrow: one day, 36 traversals on the advisor corridor and 127 overall, and no observed multimodal journeys. Section 6 gives the details and the caveats.

## 2. Research question

From the project guide:

> On verified Delhi bus corridors, does a learned segment-duration model improve held-out travel-time accuracy and connection planning compared with historical medians, under the same multimodal routing and user constraints?

We answer it in two parts.

- **Accuracy.** Held-out error of the model against the historical-median baseline, on the same split (sections 4 and 6.1).
- **Connection planning.** The advisor's own corridor leg is timed three ways: timetable, median and model. Each is compared with what buses actually did on the held-out day, as a proxy for whether a planned onward connection would be made (section 6.1). A full planner-level comparison against observed door-to-door journeys was not possible: there are no observed multimodal trips to compare with.

## 3. Data register

Every source is public, pinned by commit and checked by sha256 before use (`advisor/config/sources.json`, `data/*.dvc`). No synthetic data is used to train the model or to build the advisor. Synthetic fixtures appear only in unit tests, and the Phase 3 drift scenarios are labelled perturbations of the real replay day.

| Data | Used for | Publisher / copy | Vintage | Caveat |
|---|---|---|---|---|
| Delhi bus vehicle locations | Training labels (gate-to-gate riding times) | Delhi bus GPS archive; see the [model card](MODEL_CARD.md) | July 2019 (5 service days, 637 validated traversals) | Old; one month; feed timezone and stale-position artefacts |
| Delhi bus static GTFS (DTC + cluster) | Bus stops, trips, stage fares | Open Transit Data Delhi; byte copy at `ethanc8/delhi-gtfs @ ce95869` | June 2024 | OTD states stop times assume a constant speed |
| Delhi Metro static GTFS | Stations, trips, line shapes | OTD (DMRC); copy at `KunalK0a2/Delhi_Metro_Route_Planner @ adc43e1` | 10 Aug 2023 | Almost no weekend trips: the weekday timetable is used |
| Indian Railways stations and schedules | Passenger/MEMU trains inside Delhi | DataMeet `railways @ e0c538a` | 2016 | Some services re-timed or re-numbered since |
| Delhi boundary and 290 municipal wards | Service area and named localities | DataMeet Municipal Spatial Data `@ 9b4d1c2` (CC BY-SA 2.5 India) | Nov 2023 | Ward centres are approximations of a locality |
| OpenStreetMap via Photon / Nominatim | Typed place search (online, cached) | OpenStreetMap contributors | live | Optional; offline search falls back to wards and stops |
| OSRM on OpenStreetMap | Cab road distance and free-flow time | Public OSRM demo server | live | Light use only; rule-based fallback when unreachable |
| Fare rules | Metro slabs, bus stage fares, rail, cab/auto meter | DMRC revision of 25 Aug 2025; OTD fare_rules; Delhi Transport Dept. notification of 9 Jan 2023 | as stated | Rail fare is an assumption; cab fares are indicative |
| Emission factors | kg CO₂ per passenger-km (and per vehicle-km for cabs) | Project assumptions in `advisor_config.json` | – | For comparison only, not certification |

## 4. The bus travel-time model (Phases 1–2)

- **Labels.** A traversal is a bus crossing an entry gate and then the exit gate of a configured directional segment. There are four segments: Outer Ring Road Chirag Delhi ↔ Nehru Place, and Mehrauli–Badarpur Road Saket ↔ Khanpur. Labels come from interpolated gate crossings, never from timetables. See the [label](label_construction_report.md) and [segment](segment_specification.md) reports.
- **Features (`cold_start_v1`).** Segment, direction, route, rush-hour category, segment length, entry hour, minute of day, sin/cos of time, and three history features fixed by segment length. No live history is available at serving time. An approach-speed feature derived from the target was found to leak and was removed on 16 October ([feature report](feature_engineering_report.md)).
- **Models.** Training-set segment median (baseline), Random Forest and scikit-learn Gradient Boosting. XGBoost was proposed in Phase 1 but not implemented.
- **Splits.** By date: 1–3 July training, 5 July validation, 8 July test and holdout.

| Experiment | Gradient Boosting | Random Forest | Historical median |
|---|---:|---:|---:|
| Phase 1, corrected, 38 holdout rows (one-day retrospective) | 1.94 | 1.87 | 2.44 |
| Phase 2 validation, 102 rows (selection) | **2.47** | 2.49 | 3.24 |
| Phase 2 test, 127 rows (8 July) | **3.62** | – | 4.27 |
| Route 90 ORR eastbound subset, 36 test rows | **1.17** | – | 1.30 |

MAE in minutes. Gradient Boosting was selected on validation MAE and approved for one scope only: Route 90, Outer Ring Road eastbound. It is served by a FastAPI service in a digest-pinned, non-root Docker image. Inputs outside the approved scope return HTTP 422, and the deployed demo request returns 6.3204 min. See the [Phase 2 demo](phase2_demo.md) and the [model results summary](summaries/model_results_summary.md).

## 5. MLOps (Phase 3)

Phase 3 is a **historical replay**: 5 July is the reference day and 8 July is replayed in time order. Predictions are logged, and outcomes are revealed later. It never changes the live v1 container, the Phase 2 registry or the published image. Details: [Phase 3 guide](PHASE3_GUIDE.md), [governance](PHASE3_GOVERNANCE.md).

### 5.1 Drift detection and monitoring

- **Input drift.** PSI and Kolmogorov–Smirnov tests on request features.
- **Prediction drift.** The same tests on the predicted minutes.
- **Performance.** Per-segment CUSUM on the absolute error once outcomes arrive.
- **Data quality.** Checks on schema, service hours and registered routes.
- **Thresholds.** Calibrated by bootstrap at each window's own size. CUSUM uses a block bootstrap for at most 5% family-wise false alarms. The reference day raises no alerts after calibration.

| Replay scenario | What was detected | When |
|---|---|---|
| Natural 8 July (no injection) | Performance alarms on Mehrauli–Badarpur westbound and eastbound. Day MAE 3.62 min vs 2.47 on the reference day; the model under-predicts by about 3 min | 15:33 and 21:53 |
| Covariate shift (injected) | Input and prediction drift alerts | 296 min after onset |
| Concept drift (injected) | Performance alarms, including the ORR eastbound corridor | 49 min after onset |
| Data-quality fault (injected timezone/route fault) | Data-quality alert, then input drift and performance alerts | 12 min after onset |

### 5.2 Versioning, promotion gate, rollback

| Version | Change | Status | Holdout MAE / RMSE (min, 127 trips on 8 July) | Why it exists |
|---|---|---|---|---|
| v1 | initial release | approved, alias `previous` | 3.62 / 6.32 | The Phase 2 approved artifact, imported by hash |
| v2 | data refresh | approved, alias **`champion`** | **3.39 / 6.08** | Retrained on 1, 2, 3 and 5 July after the natural performance alarm. Same algorithm and features |
| v3 | rejected candidate | rejected, quarantined | 3.56 / 6.19 | Drill: retraining on a batch with the injected feed fault |
| v4 | **system release** | approved, alias `advisor` (after you run the script, section 8) | 3.39 / 6.08 (v2's weights) | The Delhi advisor: planner, data snapshot, fares and cab settings, with v2's weights byte for byte |

- **Promotion gate (7 checks).** v2 passed all seven:
  - training-data validation;
  - valid predictions;
  - MAE 3.386 vs champion 3.623 (6.5% better; at least 3% required);
  - MAE 3.386 vs retrained median 4.175;
  - worst segment −4.3% (limit +10%);
  - same feature schema as the API;
  - reload parity of 0.0 min.

  v3 failed data validation (service hours, registered routes), was 5.2% worse than v2, and was 17.2% worse on ORR eastbound.
- **Rollback drill.** v2 → v1 with the artifact hash verified; the demo prediction was 6.3204 min; champion restored to v2. Passed.
- **Audit log.** Append-only; every entry hashes the previous one. The advisor refuses the registry champion if the chain is broken, and the dashboard shows the chain status.
- **MLflow.** A separate Phase 3 registry (`outputs/phase3/registry/mlflow.db`) mirrors every version with its tags, gate and the `champion`/`previous` aliases. v4 adds the `advisor` alias.
- **Dashboard.** A React dashboard on port 8050 has eight pages: overview, pipeline, data, experiments, drift monitor, model registry, deployment and governance.

## 6. Evaluation

### 6.1 Does the model help the advisor? (research question)

`python -m scripts.advisor_evaluate_corridor` compares three estimates of the ORR eastbound gate-to-gate riding time against the 36 buses observed on 8 July 2019. The observed mean was 7.08 min, with a range of 4.2–15.0 min.

- **Timetable.** What the planner uses without a model: the OTD GTFS stop times, 10.9 min.
- **Median.** The historical median trained on the same days as the model.
- **Model v2.** The champion's prediction.

| Estimate | MAE | RMSE | Bias | Bus later than estimate by > 2 min | > 5 min |
|---|---:|---:|---:|---:|---:|
| Timetable | 4.09 | 4.30 | +3.82 | 2.8% | 0.0% |
| Historical median | 1.27 | 2.08 | −0.68 | 22.2% | 5.6% |
| **Model v2** | **1.03** | **1.43** | −0.45 | 16.7% | **0.0%** |

Minutes. Bias is estimate minus actual. In the peak hours (08–10 h and 17–20 h, 9 buses), MAE was 3.13 for the timetable, 2.48 for the median and 1.85 for the model.

**What this means for connection planning.**

- **The model is the most accurate estimate.** On this corridor it has 19% less error than the median and 75% less than the timetable, and it removes the median's large misses.
- **The timetable rarely makes you late, but only because it is pessimistic.** It overstates the ride by about 4 minutes, so the advisor would show later arrivals and later connections than needed.
- **Tight connections in the evening peak need a bigger buffer.** Both the median and the model under-predict in the peak: 44% of peak buses ran more than 2 minutes over the model's estimate. A transfer timed off a model-estimated leg in the peak therefore needs more than the 1-minute bus boarding buffer. This is the clearest improvement the evaluation points to (section 9).
- **The evidence is small.** It covers one segment and one day, with no significance test.

### 6.2 Recommendation quality

`python -m scripts.advisor_recommendation_quality` sends 200 random requests between Delhi ward localities. The time, budget, preference, allowed modes and cab type are random, with a fixed seed. The script checks every returned option against nine rules:

- only allowed modes are used;
- no option leaves before the requested time;
- every option arrives after it leaves;
- the fare equals the sum of the leg fares;
- the budget flag matches the fare;
- every leg starts after the previous one ends (no unreachable transfer);
- there are no negative waits;
- walks stay within the configured limits;
- vehicle changes equal rides − 1.

| Result | Value |
|---|---|
| Requests answered | 182 of 200 (3.05 options each, 555 options checked) |
| Rule violations | **0** |
| No-result cases | 18, all `no_connection`: 17 with *metro only* allowed and 1 with *bus only* (the place has no station or stop within walking distance) |
| Budget requests with at least one option within budget | 73 of 138. The others show the cheapest option and the gap |
| Options by mode | bus 229, cab 123, cab + metro 96, bus + metro 57, metro 46, metro + rail 2, cab + rail 2 |
| Plan time | mean 1.17 s, max 5.0 s (offline cab rule, cloud workspace) |

### 6.3 Tests

- **Advisor tests.** `tests/test_advisor.py`: 20 passed, 1 skipped. They cover the network build, fares (metro slabs, one ticket across an interchange, Sunday slabs, bus stage fares, free bus travel for women), the budget, estimate-source labels on every leg, the outside-Delhi and no-connection refusals, the bus model being used only on its corridor, the audit-chain requirement, place search and reverse geocoding, widening the walk when no stop is close, the API and cab mode.
- **Release tests.** `tests/test_release.py`: 6 passed. They cover v4 registration, idempotency, refusal on a failed gate or a wrong number, protection of the champion alias, and tamper detection.
- **Full suite.** It must be run in the Python 3.12 release environment, because the workspace used for this report has no FastAPI and a different Python. Run `.\.venv-dev\Scripts\python.exe -m pytest` there.

## 7. Demo cases

`python -m scripts.advisor_demo_cases` runs ten fixed requests on the real network and writes [DEMO_CASES.md](DEMO_CASES.md), with every option and leg, plus `outputs/advisor/demo_cases.json`. All are on Monday 23 November 2026 unless stated. The run committed with this report was made in a workspace that cannot load the scikit-learn 1.5.2 model, so bus times there come from the timetable everywhere. Running the script on the project machine regenerates the file with the bus model active on case 3.

| # | Case | Request | Advisor's top option |
|---|---|---|---|
| 1 | Everyday commute | Lajpat Nagar → Karol Bagh, 09:00 | Bus, 55 min, ₹15. The metro is faster (39 min, ₹43) and the cab takes 44 min at ₹269 |
| 2 | Tight budget (₹40) | Rohini → Saket, 17:10 | Two buses, 157 min, ₹30. The bus + metro option (94 min, ₹59) is flagged over budget |
| 3 | ML corridor | Chirag Delhi → Nehru Place Terminal, 17:10 | Bus 764, 15 min, ₹5. On the project machine this leg is timed by the model |
| 4 | Greenest | Dwarka → Rajiv Chowk, 08:30 | Metro Blue Line, 51 min, ₹54, 0.55 kg CO₂ against 3.65 kg by car |
| 5 | Fastest, cab allowed | Narela → Saket, 18:30 | Bus + metro, 138 min, ₹79. Cab + metro is 9 min faster but ₹407; cab only takes 161 min at ₹1,024 |
| 6 | Late night, auto | Najafgarh → Kalkaji, 23:30 | Auto-rickshaw, 83 min, ₹538 including the 25% night charge. No transit at that hour |
| 7 | Free bus for women, smart card | Mayur Vihar Ph I → ITO, 10:00 | Bus at ₹0 (pink ticket). Metro ₹28.80 with the smart-card discount |
| 8 | Suburban train | Narela (NUR) → Old Delhi, 07:00 | Train 64002, 67 min, ₹10 |
| 9 | Sunday | Hauz Khas → Kashmere Gate, Sunday 11:00 | Metro Yellow Line, 36 min, ₹32 (Sunday slab; weekday timetable note shown) |
| 10 | Outside Delhi | Cyber City, Gurugram → Karol Bagh | Refused with `outside_delhi` and the reason; no guessed route |

## 8. The advisor as model version 4

The advisor's behaviour depends on more than the model weights. It also depends on the planner code, the data snapshot, the fare and cab settings, and the web client. We therefore register what it serves as a **system release**: BusTravelTimePredictor **v4** in the same ledger and MLflow registry.

- **Weights.** v4 holds v2's weights byte for byte (same artifact sha256), so its holdout scores equal v2's.
- **Lineage.** It records a release manifest: sha256 of the planner, configuration, web client and scripts (with Windows line endings normalised), the three data-snapshot files, the pinned sources, and the fare, emission and cab assumptions. One fingerprint identifies the whole set.
- **Aliases.** The `champion` alias stays on v2, so the bus API and rollback are unaffected. v4 gets its own `advisor` alias through an audited `set_alias` step. `champion` and `previous` can still move only through promotion and rollback.
- **Release gate.** Registration writes nothing unless all eight checks pass:
  - the audit chain is intact;
  - the champion is approved;
  - the champion artifact hash matches;
  - the data snapshot was built from the pinned sources;
  - the advisor resolves the registry champion;
  - prediction parity with the deployment record;
  - two real Delhi plans succeed, with the model used;
  - the advisor tests pass.
- **Audit and rerun.** The audit log gains three entries: register, approve and set alias. Running the script again with the same files changes nothing.

On the project machine:

```powershell
.\.venv-dev\Scripts\python.exe -m scripts.register_advisor_release --dry-run   # release gate only
.\.venv-dev\Scripts\python.exe -m scripts.register_advisor_release             # ledger v4 + MLflow v4
```

The script ends by printing the exact `mlflow ui` command for your registry (port 5002).

In MLflow, version 4 of BusTravelTimePredictor carries the run `v4-system_release`, the files `release_manifest.json` and `release_gate.json`, `release.*` tags and the `advisor` alias. The dashboard's model registry page shows v4 with a "What this release packages" panel. Its governance checklist gains the control "Advisor release versioned with its model, data and code hashes".

## 9. Limitations

**Data and coverage**
- The model has only seen five days of July 2019 on four segments. It is used for one segment (ORR eastbound). All other bus times come from OTD timetables, which assume a constant speed.
- Metro times come from the weekday DMRC timetable, which is also used at weekends. Train times come from a 2016 compilation, so some trains may have been re-timed or withdrawn. No real-time data, disruptions or crowding are used.
- Places are ward centres, stations and stops offline. Typed addresses rely on OpenStreetMap search when online. A ward centre can be some distance from where a person actually starts.

**Estimates and prices**
- **Cabs.** Times depend on the public OSRM demo server and on assumed traffic factors and pickup waits. Fares are 2023 meter fares and are indicative: app cabs price dynamically, tolls and surge are not modelled, and availability is never checked.
- **Other fares.** The rail fare is an assumed minimum ordinary fare. National holidays other than Sundays are not detected for metro fares. The pink-ticket option assumes eligibility.
- **Emissions.** The factors and occupancy are assumptions. "CO₂ vs driving alone" is a potential saving, not a measured reduction.

**Planner features not implemented**
- **Arrival deadline and transfer limit.** These inputs, named in the guide, are not implemented. Users can set budget, walking limit, preference, allowed modes and cab type.
- **Waiting at the start.** Door-to-door time counts from when the option leaves. Waiting at home before a later departure is reported separately, not penalised.
- **Search window.** The search covers four hours after the requested time.
- **Peak-hour buffer.** No extra buffer is added after a model-timed leg in the peak; section 6.1 suggests one is needed.
- **Ranking policies.** These were not compared against each other with route candidates held constant; only the default policy was evaluated.

**Evaluation and MLOps**
- The corridor evaluation covers 36 traversals on one day, and the model-versus-median comparison is not significance-tested. No observed door-to-door multimodal journeys exist, so connection reliability is a proxy.
- Phase 3 is a historical replay, not live monitoring, and a user choosing an option is never treated as a travel-time label.
- The demo cases committed here were generated without the bus model (environment limits); regenerate them on the project machine.
- The MLflow registry is a local SQLite mirror; the ledger and audit log are authoritative.

## 10. Deliverables against the guide

| Guide deliverable ("What you submit") | Where | Status |
|---|---|---|
| Source-linked dataset register | Section 3; `advisor/config/sources.json`; `data/*.dvc`; [schema audit](reference/schema_audit_report.md) | Done |
| Cleaning and label-generation pipeline | `src/`; [label report](label_construction_report.md) | Done |
| Baseline and trained model | Section 4; registry v1–v2 | Done |
| Test results | Section 6.3; CI on Windows and Linux | Done (rerun the full suite in the release environment) |
| Functioning multimodal advisor (bus, metro, train, cab) | `advisor/`; [ADVISOR.md](ADVISOR.md) | Done, except arrival-deadline and transfer-limit inputs |
| Documented fare/emission configuration | `advisor/config/advisor_config.json`; [ADVISOR.md](ADVISOR.md) | Done (assumptions labelled) |
| MLOps demonstration | Section 5; dashboard; [Phase 3 guide](PHASE3_GUIDE.md) | Done (historical replay) |
| Report on assumptions and supported coverage | This report; [model card](MODEL_CARD.md) | Done |

| Milestone | Evidence | Status |
|---|---|---|
| 1 Corridors, sources, GPS audit | Schema and EDA audits, segment specification | Done |
| 2 Labels, splits, quality report | Label report, Phase 2 quality report | Done |
| 3 Baseline and candidate regressors | Phase 2 comparison, MLflow | Done |
| 4 Mode connections, calendars, transfer tests | RAPTOR network with transfer buffers; 0 unreachable connections in 555 checked options | Done |
| 5 Fares, factors, constraints, ranking | Fare/CO₂ config, four ranking policies | Partly: policy comparison and two constraints missing |
| 6 API and user interface | Advisor API (8070) and React client | Done |
| 7 Deployment, monitoring, replay | Docker v1, Phase 3 replay, dashboard, v4 release | Done |
| 8 Evaluate, document, rehearse | This report, demo cases, evaluation scripts | Done |

## 11. Reproducing the results

All commands run from the repository root on the project machine (Windows, `.venv-dev`, Python 3.12, scikit-learn 1.5.2):

```powershell
.\.venv-dev\Scripts\python.exe -m scripts.run_phase3                         # Phase 3 replay, ledger v1-v3, MLflow
.\.venv-dev\Scripts\python.exe -m scripts.advisor_fetch_data                 # pinned Delhi data
.\.venv-dev\Scripts\python.exe -m scripts.advisor_build_network
.\.venv-dev\Scripts\python.exe -m scripts.advisor_check                      # data, model parity, geocoder, API
.\.venv-dev\Scripts\python.exe -m scripts.advisor_evaluate_corridor          # section 6.1
.\.venv-dev\Scripts\python.exe -m scripts.advisor_recommendation_quality     # section 6.2
.\.venv-dev\Scripts\python.exe -m scripts.advisor_demo_cases                 # section 7
.\.venv-dev\Scripts\python.exe -m scripts.register_advisor_release           # section 8
.\.venv-dev\Scripts\python.exe -m pytest
```

Outputs from the evaluation scripts go to `outputs/advisor/`, which is git-ignored. `docs/DEMO_CASES.md` is committed.
