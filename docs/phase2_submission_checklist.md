# Phase 2 validation and submission checklist

Audit date: **November 9, 2026**. Inspected source: `2358995067f71e4c28057bc4ddf4c97f77d3429b`. Reference: the supplied **Transportation Advisor Phase 2 Implementation Guide**, 13 pages. The Phase 1 presentation was also read for proposal/history alignment. Neither external PDF is copied into this repository. Exact source hashes, executed results and local evidence locations are in the [sanitized record](results/2026-11-09-validation/summary.json).

This checklist is the requirement audit, not a declaration that every guide stage is complete. Equivalent implementation paths count; suggested filenames and example commands in the guide are not treated as literal requirements. Optional history-store upgrades and the median-response branch are not applicable to this GB cold-start release. The guide's old PR organization is historical; the team now works directly on main per [CONTRIBUTING](../CONTRIBUTING.md).

## 1. Execution evidence and environment

The original November 9 laptop deployment is preserved in ignored `outputs/local_setup/verification-20261109-131834/`. It served the approved model by GHCR digest on `127.0.0.1:8001`: eight runtime checks and smoke passed, health/prediction returned 200, invalid requests returned 422, and artifact hash/model type matched the approved Gradient Boosting v1. Fresh non-mutating checks during this audit are recorded separately; no real-data model was retrained or replaced.

Automated suite execution and dependency qualifications are recorded in the [validation JSON](results/2026-11-09-validation/summary.json). The first complete execution produced **78 passed, 2 failed** in 106.43 s with MLflow 3.17.1: its skops serialization rejected tree types in two registration tests. Installing the declared CI requirements first failed on unavailable `anyio==4.16.0`. A second isolated run with MLflow 3.1.4 produced **73 passed, 7 setup errors** in 34.33 s because the borrowed SQLAlchemy 2.1.4 lacked `FallbackAsyncAdaptedQueuePool`. **Final execution: 80 passed, 0 failed/errors/skips, 61 warnings in 74.95 s**, after installing the repository-pinned MLflow/MLflow-skinny 3.1.4 and SQLAlchemy 2.0.57 in the isolated test environment. Deprecation/schema warnings remain. Both earlier failed runs and install logs are preserved. No application change or trust-check bypass was used.

The test interpreter is Python 3.12.5. Pytest was installed in an ignored, isolated environment; existing development libraries were borrowed read-only. This is not the original Python 3.12.14/Linux/sklearn 1.5.2 release environment. The running image's versions and artifact identity are verified independently. Test fixtures train tiny models and create temporary SQLite registries; that is not retraining the approved model or reproducing its real-data metrics.

Historical counts remain separate: the November 6 approval snapshot records 29 tests/12 checks; the captured PDF records 58 tests; November 7 reproduction documentation records 80 tests/16 checks and 127 prediction comparisons. The November 6 snapshot predates the current 16-check schema and is not a current registrar input unchanged.

## 2. Requirement-by-requirement audit

Status key: **V** fully implemented and verified for the stated scope; **I** implemented/inspected but not executed here; **P** partially implemented; **M** missing; **B** blocked by unavailable data, credentials or infrastructure. A fixture check verifies that fixture behavior, not the original model accuracy or a shared production registry. References below are repository-relative paths; raw logs remain local and the linked JSON provides sanitized results.

| ID / PDF page | Requirement | Status | Evidence / exact limit |
|---|---|---|---|
| 01 / 1 | End-to-end DVC → approval → registry → image → deployed prediction | P | Raw pointer and historical records link parts of the chain; actual published image/API verified. No protected Actions deployment or complete baked lineage. |
| 02 / 1 | Deploy riding-time predictor for four directional segments | P | `src/features/segment_config.py` contains four; `src/api/main.py` permits only approved Route 90 eastbound. |
| 03 / 1-2 | Inherit batch pipeline; use Python/pandas/SQLite/DVC/DagsHub/Git, sklearn/Pytest/MLflow, Joblib/API/Docker/GHCR/Compose | V | Source and dependency inspection; data SQL, automated fixtures and real Docker/API checks establish their respective scopes. Tool use alone does not complete later requirements. |
| 04 / 2 | Phase 2 branch / reviewable changes and compatible environments | P | Historical branches/PRs merged; CI and image pin Python 3.12.14. Windows lock installation blocked; current team workflow intentionally uses main. |
| 05 / 2 | Team can read data remote and registry, create workflows and push GHCR | P | Present image pull and explicit known-object DVC cloud status passed; historical workflows succeeded. Automatic DVC stage index is empty; original/shared registry and every teammate permission unverified. |
| 06 / 2 | Assigned Linux host, SSH and HTTPS demo URL | B | No assigned VM/SSH/ingress available here. Localhost is not that infrastructure. |
| 07 / 3 | Verified raw sample, DVC pointer/hash and private credentials | V | `data/raw/2019-07-01.db.dvc`, `.dvc/config`; read-only integrity, MD5/SHA-256 and inventory match. Local credential values were not printed or committed. |
| 08 / 3 | Reproduce baseline acquisition/labels/features/train and capture actual metrics | B | Acquisition and pipeline code exist (`src/data/download_sample.py`, `src/features/build_labels.py`, `src/models/train.py`). Real-data training intentionally not authorized; only data checks and fixture tests executed. |
| 09 / 3 | Capture seed, Git/data identity, runtime, label counts, model/result paths | P | Corrected provenance and cold-start `run_report.json` code capture most fields. No available original multi-day raw→processed lineage on this laptop. |
| 10 / 3,9 | Pinned tested training/serving environments | P | `requirements-serve.lock.txt`, `requirements-ci.txt`; published Linux environment checked. `requirements.txt` has minimums; exact Windows CI install failed. |
| 11 / 4 | Shared evaluation/request feature adapter, ordered 12-feature contract | V | `src/features/build_features.py` shared by trainer/API; `tests/test_models.py` asserts columns, order, dtypes and encoded equality. |
| 12 / 4 | String route IDs in CSV and API, aware entry time, IST conversion | V | `load_training_features`, `BusPredictionRequest`; model/API fixture tests and live HTTP validation. |
| 13 / 4 | Catalog-resolved route/direction/length, supported coverage validation | V | `src/api/bundle.py`, `src/api/main.py`, `segment_config.py`; unsupported pair receives 422. Scope is the one approved pair. |
| 14 / 4 | Same named cold_start_v1 policy at fit/evaluate/serve | V | `engineer_features(..., use_observed_history=False)`; two length/22*60 durations, zero count; parity fixtures and live policy verified. |
| 15 / 4-5 | Exclude target, exit and completed-trip speed; no future-history leakage | V | Explicit feature lists and `tests/test_feature_engineering.py` mutation/overlap tests. Optional live as-of history store not supplied or required for chosen cold-start mode. |
| 16 / 5 | Reject naive time, unknown combination and extra target | V | `tests/test_api.py`; real laptop 422 responses also recorded. |
| 17 / 5 | Incomplete label across fit cutoff cannot train | V | `split_by_date` and `test_cold_start_split_excludes_labels_finishing_at_cutoffs`. |
| 18 / 5 | Passing/losing/malformed/missing gate fixtures and nonzero CLI failure | P | `tests/test_quality.py` covers pass, tampering and invalid JUnit/store. Genuine losing-candidate fixture and explicit CLI exit regression test are absent. |
| 19 / 5 | Artifact reload, positive finite output and verify hash before load | V | `load_bundle`, tampered-hash TestClient test, actual v1 hash/model check and positive HTTP prediction. |
| 20 / 5 | Automated missing/corrupt/incompatible artifact readiness cases | P | Corrupt hash tested; code handles load exceptions. Dedicated missing-file/incompatible-manifest regression cases absent. |
| 21 / 5 | API unavailable → readiness/inference 503 | V | `test_hash_mismatch_makes_api_unready` exercises both endpoints with corrupt fixture. This does not cover every prediction-time exception. |
| 22 / 5 | Real-release HTTP smoke: readiness/version/prediction/unsupported segment | V | `scripts/smoke_api.py` checks route; `scripts.verify_deployment.py` additionally checks segment/time. Both ran against the real image. |
| 23 / 6 | Earlier fit / later validation and final test; labels complete by cutoff | V | `src/models/train_cold_start.py`; cutoff fixture exercised. Historical real-data scores remain external-to-this-run evidence. |
| 24 / 6 | Frozen split with eligible row/journey IDs and grouped journey legs | P | Input hash/dates/counts/seed/excluded boundary count exist; no explicit eligible-ID or journey-group split manifest. |
| 25 / 6 | Median/RF/GB on same rows; train-only preprocessing; validation selection | V | Candidate factory and cold-start trainer inspected; existing training fixtures exercise all three. Legacy `train.py` still selects by test MAE and is not the approval route. |
| 26 / 6 | MAE/RMSE, counts and errors by supported segment/time period | P | Trainer writes `test_by_segment.csv`; committed quality snapshot includes overall/approved-route scores. Complete per-slice CSV and run report absent here. |
| 27 / 6 | Predeclared gate, minimum samples, weak/sparse segment review | P | `check_quality.py` requires candidate improvement, schema/provenance and >=2 demo rows. Prior declaration and all-segment risk review not established. |
| 28 / 6 | Approve only pass; retain failed candidate/report or incumbent | P | Quality writes failure report/nonzero; registrar blocks bad approval. No general incumbent/median promotion workflow; local deployed incumbent remains intact. |
| 29 / 6 | Historical limitations and model record with coverage/units/fallback | V | `docs/results/phase2-v1/quality_report.json`, API/model manifest and demo guide label historical Route 90, minutes and cold-start behavior. |
| 30 / 7 | Shared persistent MLflow backend; training/export URI and runner access | M | Approval/export explicitly require local SQLite and file artifacts; no shared-registry release integration. |
| 31 / 7 | Log params, data/splits, code SHA, versions, metrics and quality to MLflow | P | Cold-start logs seed/hash/policy/cutoffs/metrics/artifacts to `BusTravelTime-ColdStart`; complete required logging and guide experiment name not implemented. |
| 32 / 7 | Numbered BusTravelTimePredictor READY, correct run, signature/example, approval | V | `tests/test_registration.py` passed with temporary SQLite registry, signature/example and reload/export parity. This verifies fixtures; original release registry remains absent. |
| 33 / 7 | Verify original registry/run and full registered prediction parity here | B | Original `outputs/phase2_registry/tracking.db` and artifacts absent; do not create a fake original UI. Temporary-registry tests are separate. |
| 34 / 7 | Export approved numbered version; reload export against MLflow | P | `export_serving_bundle.py` verifies READY/run/hash then copies checked Joblib. Registrar checks MLflow reload; exporter does not itself compare reloaded exported bytes to MLflow predictions. |
| 35 / 7,13 | Manifest version/run/source/DVC/policy/schema/artifact/environment hashes | P | `BundleManifest` contains model/version/policy/features/hash/sklearn/route/segment; lacks run ID, Git/DVC/schema/lock identities. |
| 36 / 7 | Trusted bundled loading; registry secrets outside API | V | Running API uses local `/app/release`, verified checksum and schema; no MLflow dependency/credential needed at runtime. |
| 37 / 8 | FastAPI/Pydantic/Uvicorn; load once in lifespan/state | V | `src/api/main.py`, actual container startup, fixture API checks. |
| 38 / 8 | /health model identity, /predict/bus response fields and validation | V | Live HTTP 200/422, model v1, cold_start_v1, finite positive duration; typed response. Median-source conditional not applicable to chosen GB release. |
| 39 / 8 | All unavailable inference returns 503 | P | Missing bundle/invalid numeric result handled; exceptions thrown by `model.predict()` are uncaught and can become 500. |
| 40 / 8 | /docs Swagger, request example and response contract | P | /docs HTTP 200 and typed contract exist. Exact working example is in demo guide, not explicit OpenAPI example metadata. Browser rendering not retested here. |
| 41 / 8 | Request ID, route/segment, version/policy, status/latency and readiness logs | P | Uvicorn access/startup logs and bundle-load exception log exist; structured context/request IDs/latency absent. |
| 42 / 9 | Locked runtime, target Linux compatibility, exclude training/test tools | V | Dockerfile uses serving-only lock; current image pip/versions checked separately in validation record; suite runs on host fixtures, not serving container. |
| 43 / 9 | Bundle/code in image; model export ignored but available to build | V | Actual `/app/release` model loaded; Dockerfile copies ignored `outputs/phase2_serving` files. A source build still requires that local bundle. |
| 44 / 9 | Lean context excluding Git/venv/data/runs/secrets, retaining bundle | I | `.dockerignore` allowlist inspected; a fresh source-image build was not performed here. |
| 45 / 9 | Pinned base digest, nonroot user, explicit bundle path and loadability | V | Dockerfile pins base; running image/container identity and healthy nonroot startup checked. |
| 46 / 9 | Build and HTTP-check real artifact locally | P | Published-image real artifact tested on laptop; source build not rerun and local export bundle absent. |
| 47 / 10 | PR/push CI with pinned Python/actions, fixtures and least privileges | V | `.github/workflows/ci.yml`; GitHub run `42342969930` for inspected main is success. No new PR is required by current team workflow. |
| 48 / 10 | Manual release from main accepting approved model version | M | `release.yml` triggers fixed tag `phase2-image-v1`, without main restriction or version input. |
| 49 / 10 | Release verifies registry/quality/code compatibility and exports with parity | P | Exact-commit CI and hardcoded bundle hashes/real smoke enforced; two secrets restore prebuilt v1. No fresh MLflow/quality/export verification. |
| 50 / 10 | GHCR publish with version+SHA tags, digest and post-publish smoke | P | Historical release jobs checked success; exact digest pulled/smoked here. Only v1 tag, no code-SHA tag. |
| 51 / 10 | Restricted bundle handoff, pinned actions, minimum permissions | P | Export/build in one release job; pinned actions and package permissions. Bundle is repository-secret-held, with no protected release environment. |
| 52 / 10-11 | Protected deploy dependency, SSH/host key, VM read-only pull credential | M | No deploy job/environment/SSH configuration or VM package credential wiring. |
| 53 / 11 | Compose pinned digest, loopback port, restart and healthcheck | V | `deploy/compose.yml`, inherited Dockerfile healthcheck; healthy 127.0.0.1:8001 container verified. |
| 54 / 11 | Validate image, stable project, previous record and serialized activation | V | `scripts/deploy_api.py` validation/state/lock; real first deployment plus mocked recovery tests. This is local, not an Actions VM deploy. |
| 55 / 11 | Wait readiness, endpoint/version smoke before activate; rollback/recheck | P | First deployment/smoke verified; `tests/test_deploy.py` covers failure recovery. No live version rollback or restart/reboot durability exercised. |
| 56 / 12 | Reviewable changes, lineage→gate→registry→API→delivery demo | P | Historical PRs and updated existing demo sequence available. Original registry UI and protected deploy job cannot be shown live here. |
| 57 / 12 | Hand-in repo, quality/splits, model/run, Actions, digest, URL, response, limits | P | Existing snapshots/PDF and November 9 JSON cover local demonstration. Assigned HTTPS URL and full real-data reproduction evidence unavailable. |
| 58 / 13 | External release record with actual identities, smoke timestamp and rollback target | P | `deploy/model-v1.json` + historical quality/registry + sanitized laptop JSON; no previous real release/assigned service. Missing baked lineage remains explicit. |

## 3. Evidence to show faculty

- [Project chronology](summaries/pipeline_overview.md): actual Git dates/authors and planned versus implemented scope.
- [Corrected Phase 1 benchmark](results/2026-10-16-corrected/README.md): 12 inputs and leakage correction; use its CSV instead of old slide scores.
- [Historical Phase 2 quality](results/phase2-v1/quality_report.json) and [registry](results/phase2-v1/registration.json): original model approval, not this laptop's new training run.
- [Captured historical PDF](../output/pdf/Phase_2_Demonstration_Evidence.pdf): earlier screenshots and 58-test record, unchanged.
- [November 9 sanitized record](results/2026-11-09-validation/summary.json): actual laptop HTTP/container/data/test results, limitations and preserved local evidence paths.
- [Inspected-main CI](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/actions/runs/42342969930) and [v1 image release](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/actions/runs/42330318360): GitHub status inspected, not rerun or republished during this audit.

Use the single [faculty walkthrough](phase2_demo.md#12-november-9-laptop-verification-and-faculty-sequence). Preserve the existing instance's custom state directory. New evidence uses new filenames; never rerun deployment simply to display a check.

## 4. Priorities before claiming full Phase 2 completion

1. Restore exact-lock availability and document reproducible platform environments; preserve the failed runs alongside the passing fixture-registry tests, without permissive serialization workarounds. Make the processed multi-day data and raw-source lineage retrievable by teammates.
2. Complete shared MLflow release verification, immutable split IDs and the full baked manifest. Retain the incumbent when a candidate fails; add missing/losing/incompatible-artifact regression cases.
3. Obtain assigned infrastructure and implement protected Actions-to-VM/HTTPS deployment with captured smoke and live rollback evidence. Local Docker success does not satisfy this requirement.
4. Expand approval/serving to the guide's four directional segments only after adequate per-slice evaluation; add structured request logs and consistent inference-failure handling.
5. Evaluate independent/new traffic before claiming current accuracy. Multimodal routing, fares, emissions and UI remain later milestones.

## 5. Submission and safe Git synchronization

- [ ] Show the actual latest test outcome, including dependency/failure qualifications.
- [ ] Verify current health/prediction/digest with the existing state file; retain timestamps.
- [ ] Explain historical metrics, approved scope and unavailable original MLflow store.
- [ ] Inspect every changed/staged file; no raw data, models, tokens, absolute user paths or local databases.
- [ ] Fetch before commit and immediately before push; integrate only conflict-free changes, never force-push.
- [ ] Commit intentional documentation/evidence directly to main; record SHA and push result.

No missing application features were implemented during this audit. The running approved model and original local evidence are preserved.

**Environment limitation:** the final fixture suite passed, but `pip check` on the mixed test environment still failed (missing greenlet and MLflow constraints on pandas, pyarrow, cachetools, importlib-metadata and packaging). Do not use this mixed environment to approve or retrain a real release. The running Linux image independently passed its lock comparison and `pip check`. Full logs and exact versions are recorded in the sanitized validation JSON.
