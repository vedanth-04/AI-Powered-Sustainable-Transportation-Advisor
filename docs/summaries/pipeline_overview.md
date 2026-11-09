# Project evolution: Phase 1 to Phase 2

This is the navigation and chronological progress record. Dates below are Git author dates in IST; author names are the literal Git metadata, not an inference about sole ownership. Earlier technical reports use internal stages called "Phases 1-7". Those stages belong to the academic **Phase 1 batch pipeline**; they are not seven academic milestones.

## Phase 1: problem, data and experiments (October 2026)

The Phase 1 presentation, `Experiential_Learning_Phase_1_Presentation.pptx.pdf`, proposes a multimodal advisor balancing complete journey time, budget, walking constraints and emissions. The implemented ML component is narrower: predict bus-segment riding time from historical GPS. Waiting, transfers, fares, other modes and a user journey interface are planned, not demonstrated here.

| Git date (IST) | Commit / Git author | What changed and evidence |
|---|---|---|
| Oct 15, 10:04 | `d85bd63` / Vedanth | Project foundation, problem definition and team documentation |
| Oct 15, 10:30 | `3c4a488` / Vedanth | Selective archive extractor and [schema audit](../reference/schema_audit_report.md); sample acquisition and integrity evidence |
| Oct 15, 10:35 | `8d557b5` / Vedanth | DVC initialization and [July 1 pointer](../../data/raw/2019-07-01.db.dvc) |
| Oct 15, 10:54 | `7702141` / Vedanth | EDA notebook and findings; [current corrected EDA overview](../eda_report.md) |
| Oct 15, 12:00 | `5250d9c` / Vedanth | DagsHub S3-compatible team storage and [onboarding guide](../reference/dvc_team_setup.md) |
| Oct 15, 16:32 | `781470f` / Vikasyk | Fleet-wide [EDA audit](../reference/eda_audit_report.md) and [segment specification](../segment_specification.md) |
| Oct 15, 19:53 | `bb7038c` / Vikasyk | Cleaning, gate labels, feature engineering, median/RF/GB training, MLflow and tests |
| Oct 16, 05:48 | `84ac497` / Vikasyk | Removed target-derived approach-speed leakage; added measured feature importance |
| Oct 16, 07:12 | `e9fa9ae` / Vikasyk | [Corrected benchmark and provenance](../results/2026-10-16-corrected/README.md) |
| Oct 16, 11:22 | `e9abe21` / Vikasyk | Restored original audit notebooks; this is the Phase 2 guide's starting snapshot |

**Implemented:** acquisition, DVC identity, two audit/EDA notebooks, four configured directional segments, interpolation-based labels, 12 input features, heuristic and tree regressors, error/importance plots and MLflow integration. [Label report](../label_construction_report.md), [feature specification](../feature_engineering_report.md).

**Historical result:** 152 traversals across four segments, 114 training and 38 holdout rows. Corrected RF MAE 1.8694 minutes; GB 1.9427; median 2.4412. Selection used the same holdout, so this is a one-day retrospective benchmark, not an untouched final evaluation. Runtime was Python 3.9.13 / scikit-learn 1.4.2, below the declared minimum sklearn version; preserve that qualification.

**Presentation corrections:** the slides' 0.62-minute GB result is superseded by the leakage correction; slide RMSE values conflict with the old repository table. XGBoost was proposed, but scikit-learn Gradient Boosting is implemented. The slides' full-month count of 57,992,518 records across 31 databases has not been reproduced from this laptop's single daily sample. Use the committed corrected CSV/provenance when quoting metrics. No new slide deck or PDF replaces the original.

## Phase 2: approved historical model to local API (November 2026)

| Git / evidence date | Commit / attribution | Progress |
|---|---|---|
| Nov 6, 12:51 IST | `dc0571e` / Vikasyk | Date-separated cold-start comparison, quality check, checked export, FastAPI and tests |
| Nov 6, 06:55 UTC | Historical quality record | GB approved for Route 90 eastbound; 408 train / 102 validation / 127 test rows; [quality](../results/phase2-v1/quality_report.json) and [registry](../results/phase2-v1/registration.json) snapshots |
| Nov 7, 07:48 IST | `ef0832f` / Vikasyk | CI tests and synthetic container smoke |
| Nov 7, 08:01 IST | `44d31e1` / Vikasyk | Real v1 image release; [pinned image](../../deploy/model-v1.json) |
| Nov 7, 08:42-09:09 IST | `847add0`, `33a0fc7`, `2438d0f` / Vikasyk | Scripted local Compose deployment, recovery tests, runtime verification and captured PDF |
| Nov 7, 10:41 IST | `f80da54` / Vikasyk | Isolated approval/registration reproduction command; documentation records 80 tests and 16 checks on the 637-row input |
| Nov 7, 10:59 IST | `2358995` / Vikasyk | Remaining Phase 2 work merged into main |
| Nov 9 | Vedanth / this laptop's setup and verification | Safe fast-forward to `2358995`, Docker/WSL setup and approved-image verification; 8/8 checks, valid prediction and 422 validation. [Sanitized record](../results/2026-11-09-validation/summary.json) |

The November 6 record's UTC evaluation time precedes the source commit's author time. Its `git_head` is the prior checkout and its source hashes identify evaluated working-tree files; do not equate that field with the later release image source revision.

**Implemented:** shared `cold_start_v1` features, validation-based selection, local SQLite registry checks/signature, Joblib export, strict API validation, nonroot digest-pinned Docker image, GitHub CI/GHCR release, and locally initiated Compose deployment with recovery logic.

**Actually observed on this laptop:** the approved Gradient Boosting v1 artifact hash, container digest/health, `/health`, real Route 90 prediction `6.320402254818158`, unsupported requests returning 422 and repository smoke/verifier success. The short [model summary](model_results_summary.md) separates these from historical accuracy.

**Not reproduced with real data here:** the 637-row multi-day input, original MLflow registry/store, real-data training and approval. Tests may train small synthetic fixtures and temporary registries; those do not replace or validate the approved model's historical accuracy. The November 9 full suite passed 80 tests with 61 warnings after isolated dependency alignment; two earlier failed attempts are retained. The [requirement audit](../phase2_submission_checklist.md) records the exact environment and gaps.

## Documentation map and preservation decisions

November 9, subsequent implementation Batch A: replaced open-ended development requirements with a complete CPython 3.12 test lock, separate from serving; added a non-overwriting PowerShell setup helper, installed-pin verification and Windows/Linux CI. A fresh local environment passed pip check and all 80 tests (23 warnings), without borrowing from or changing the original `.venv`. Earlier audit failures remain recorded.

- Detailed EDA/label/feature reports explain methodology; summaries provide short faculty explanations, not competing result tables.
- `docs/reference/` retains the original scaffold, stage plans, schema audit, fleet audit and DVC setup. Its [index](../reference/README.md) labels historical context.
- `docs/model_benchmarking_report.md` deliberately retains superseded pre-correction results. Current Phase 1 metrics live in `docs/results/2026-10-16-corrected/`; Phase 2 v1 approval is in `docs/results/phase2-v1/`.
- The [demo guide](../phase2_demo.md) is the single faculty walkthrough. The [reproduction guide](../phase2_reproduction.md) is for separately authorized model work, not a prerequisite for running the published image.
- Raw data, local tokens, models, SQLite stores and full command logs remain ignored. The small November 9 JSON is a sanitized tracked summary, not a second raw evidence archive.

## Pending milestones

First close the Phase 2 guide gaps: four-segment approved coverage, shared registry/release lineage, complete manifest, explicit missing/losing fixture coverage, structured service logs and protected VM deployment. Then evaluate new independent/current traffic data and build timetable-to-segment mapping. Multimodal journey routing, fares, emissions ranking and the journey UI follow later. A localhost demo is not a public deployed service.
