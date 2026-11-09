# Reproduce the Phase 2 model approval workflow

The deployed image demonstrates the approved historical Route 90 model. The commands here repeat model testing, training, quality checks, registry registration, export, and an in-process FastAPI check in a new local workspace. Each execution uses a separate SQLite registry. Publishing another image or changing the live deployment remains a separate release action.

## Prerequisites

### Available daily-sample DVC pipeline

With the clean environment installed and `data/raw/2019-07-01.db` restored using your existing private DVC credentials:

```powershell
# Prepend the new interpreter so DVC stage commands use the same environment.
$env:PATH = (Join-Path $PWD '.venv-dev/Scripts') + ';' + $env:PATH
python -m dvc status
python -m dvc dag
python -m dvc repro
python -m dvc status
```

`dvc.yaml` runs real existing corridor cleaning/label extraction, then `cold_start_v1` feature engineering. New DVC-managed outputs live only under `data/processed/sample_cold_start/`; existing corrected/historical outputs are preserved. The raw database is checked against its unchanged MD5/size pointer before processing. Deterministic CSVs and JSON record raw SHA-256/DVC identity, exact pointer and source hashes, lock hash, row count, feature schema and output hashes. No timestamps or personal absolute paths enter this metadata. `dvc.lock` records the dependency/output DAG; only small configuration and lock metadata are committed. No data was uploaded to the remote.

The discovery bug came from Dulwich interpreting `data/raw/*` as matching the directory's trailing slash and pruning it before finding `.dvc` files. Requiring a nonempty basename (`?*`) preserves data ignores and pointer discovery; a temporary Git/DVC regression test verifies both. An initial directory-negation attempt failed that test and was replaced. DVC also rejects `.dvc` pointer files as explicit stage dependencies: the stage depends on the actual database, with pointer verification in the preparation code.

The real July 1 run produced 152 traversals and feature rows. A repeated `dvc repro` skipped both stages and status was up to date. This is the one-day preparation pipeline, **not** the missing 637-row multi-day input or approved training reproduction. No training stage is invented for unavailable inputs. Raw hashes and the original pointer are unchanged; obtaining the original multi-day datasets and verifiable processing lineage is still required. Cross-platform byte hashes may change with Git newline settings and numerical runtime; retain the recorded environment and validate outputs rather than assuming identical bytes.

### Clean development/test environment (November 9 implementation)

Use CPython 3.12 and a new environment; keep the original `.venv` and approved Linux serving image. From the repository root:

```powershell
powershell -File scripts/setup_dev.ps1 -RunTests
# Subsequent commands use the new interpreter explicitly:
.\.venv-dev\Scripts\python.exe -m pip check
.\.venv-dev\Scripts\python.exe -B -m scripts.verify_environment --require-venv
.\.venv-dev\Scripts\python.exe -B -m pytest tests -q
```

The setup helper refuses an existing destination; use `-EnvironmentPath .venv-dev-2` for another isolated installation. It records a transcript, package consistency, lock validation and optional JUnit results under ignored `outputs/local_setup/environment-<unique-id>`. No activation or global Python changes are required. `requirements-dev.in` records direct dependencies; `requirements-dev.lock.txt` pins the full resolved environment, including platform markers. Regenerate only in a fresh environment and validate with pip check and tests. Notebook tools are optional and excluded from this model/test environment; install them separately if needed. Windows and Linux CI use this same test lock; Docker retains `requirements-serve.lock.txt` unchanged.

The earlier host/mixed environment fails because its MLflow/SQLAlchemy versions and pandas/pyarrow/cachetools/importlib-metadata/packaging constraints conflict, with greenlet missing in the borrowed test environment. The clean environment pins MLflow/skinny 3.1.4, SQLAlchemy 2.0.57 and compatible scientific libraries, resolving dependencies normally. Earlier audit failures below remain historical evidence. A development lock does not prove byte-for-byte reproduction of the unavailable historical training store.

Use Python 3.12 with an explicitly recorded test environment. Do not assume an existing `.venv` matches the original release. For a fresh clone, create a Python 3.12 environment and install `requirements-ci.txt`; it includes the inference dependencies and the additional training/test tools. Run commands from the repository root. Docker is used for the already published API deployment; this model reproduction command runs in Python.

Supply the processed traversal CSV locally. The demonstrated input is `data/processed/phase2_cold_start/traversals.csv`, with 637 traversals and SHA-256 `243f568e1abc9d29e2fe9f665df36302a2aff61851438871de7ea4643dd5267b`. The data file is ignored by Git. A fresh clone needs the corresponding processed data from the project's data workflow before it can reproduce training. The committed historical reports are evidence of the earlier evaluation, and do not replace the input dataset.

## Run all stages

Choose a new output directory for every attempt:

```powershell
.\.venv\Scripts\python.exe -m scripts.reproduce_model_workflow `
  --traversals data/processed/phase2_cold_start/traversals.csv `
  --validation-start 2019-07-05 `
  --test-start 2019-07-08 `
  --output-dir outputs/phase2_reproduction_demo
```

If the output directory already exists, the command stops before running tests or model operations. Omit `--output-dir` to use a new timestamped directory automatically. A failure leaves the new run's partial results and `workflow_report.json` available for inspection; retry with a different directory.

On Windows, test fixtures use a short operating-system temporary directory so MLflow's nested artifact paths fit. Its location is recorded as `pytest_temp_dir` in the workflow report. JUnit XML and model workflow evidence remain under the chosen output directory.

| Stage | Tools | What happens |
|---|---|---|
| Tests | Python, Pytest | Run the repository test suite and write JUnit XML. Failure stops the workflow before training. |
| Training | pandas, scikit-learn, Joblib, MLflow | Rebuild cold-start features, use date-separated splits, fit median/Random Forest/Gradient Boosting candidates, select the tree on validation MAE, and log the runs and artifacts. |
| Quality approval | Python, pandas, scikit-learn, MLflow | Recompute scores from the saved artifacts; verify input, split, feature, test-result, runtime and MLflow provenance; require improvement over the median and valid predictions. |
| Registry | MLflow Model Registry | Register the passing candidate in the new local SQLite store, reload that numbered version, compare predictions, and attach approval/checksum tags after verification. |
| Export | Joblib, SHA-256, MLflow client | Use the existing exporter to produce a model and manifest linked to the checked registry version. |
| API check | FastAPI, Pydantic, TestClient | Load that new bundle in process; verify readiness, a Route 90 prediction, and HTTP 422 for an unsupported route. |

The test dataset is used to assess the selected candidate and decide whether it meets the historical demonstration gate. Model selection uses the validation split. Repeating this workflow on the same July 2019 observations is a reproducibility exercise; it does not add a new independent accuracy evaluation or establish present-day transport performance.

## Inspect the results

```text
outputs/phase2_reproduction_demo/
  workflow_report.json       Overall result, completed stages, and API response
  pytest.xml                 Actual test outcome for this execution
  registry/
    tracking.db              This run's independent MLflow store
    artifacts/               Locally logged run/model artifacts
  training/
    run_report.json          Input hash, splits, metrics and MLflow run IDs
    model_comparison.csv     Validation comparisons and selected test results
    test_by_segment.csv      Historical segment error breakdown
    quality_report.json      Passing or failing checks and supporting evidence
    registration.json        Created only after successful registration verification
    historical_median.joblib
    tree_candidate.joblib
  serving/
    manifest.json
    model.joblib
```

All files above are generated locally under the ignored `outputs` directory. The report contains a local registry URI, so moving the entire run to another machine also requires handling MLflow's artifact paths. Teammates can reproduce their own local run from the same input data and environment.

A model version number belongs to its registry. Version 1 in this new store is an independent reproduction record. It does not replace the original registry's version 1, change `deploy/model-v1.json`, or publish an image. Check the run ID, artifact checksum, registry URI, and scope together when identifying a model.

## Run quality and registration separately

For an existing training run created by `src.models.train_cold_start`, supply the actual successful test report:

```powershell
.\.venv\Scripts\python.exe -m src.models.check_quality `
  --run-dir outputs/phase2_reproduction_demo/training `
  --pytest-xml outputs/phase2_reproduction_demo/pytest.xml

.\.venv\Scripts\python.exe -m src.models.register_checked_model `
  --run-dir outputs/phase2_reproduction_demo/training
```

These standalone commands are for a run that has not already completed those stages. The quality checker saves a report even when a check fails and exits with an error. The registrar requires a passing report and matching input/report/artifact identities before it writes to the registry. Both refuse to overwrite their existing report files. To rerun the complete process, choose a new output directory rather than modifying an earlier approval record.

To export a separately registered result:

```powershell
.\.venv\Scripts\python.exe -m src.models.export_serving_bundle `
  --release-dir outputs/phase2_reproduction_demo/training `
  --bundle-dir outputs/phase2_reproduction_demo/serving
```

For the existing classroom deployment, continue to use `scripts.deploy_api` and `scripts.verify_deployment` with the approved published image. Keep the historical demonstration scope and the recorded evidence timestamps visible when presenting the results.

## Recorded validation on 7 November 2026

The complete command passed on the existing 637-traversal input in `outputs/phase2_reproduction_20261107_complete`. Its recorded result contains:

- 80 passing tests, with no failures, errors, or skipped tests.
- All 16 required model-quality checks passing.
- Gradient Boosting selected by validation MAE of 2.473947 minutes; overall test MAE of 3.622576 minutes.
- An independent local registry version verified against all 127 held-out predictions.
- A successfully exported bundle whose model SHA-256 matches the historical v1 artifact: `b26d1a45f8e97278b8be70eef9c6c88e39b7d52537d55bea6a206b3391934a88`.
- An in-process prediction of 6.320402254818158 minutes, readiness success, and HTTP 422 for an unsupported route.

The original registry database, serving bundle, deployment state, and published-release metadata were hash-checked before and after this reproduction and remained unchanged. The earlier 58-test PDF captures the preceding demonstration stage; this section records the subsequently expanded workflow tests.


## November 9 validation qualification

The processed 637-row CSV and original registry/artifact store are absent on the second laptop. Real-data reproduction was therefore not attempted; the approved image was preserved. The original 29-test quality snapshot and 58-test PDF precede the November 7 documented 80-test reproduction and the [November 9 audit](phase2_submission_checklist.md).

Installing `requirements-ci.txt` in a new Windows environment failed on unavailable `anyio==4.16.0` from the configured index. The audit records actual alternative test environments and outcomes rather than silently changing the committed lock or claiming exact release parity. Existing tests train synthetic fixtures and isolated SQLite registries; they do not retrain the approved model.

The complete November 9 existing suite ultimately passed **80 tests** after isolated MLflow/MLflow-skinny 3.1.4 and SQLAlchemy 2.0.57 installation. Earlier runs failed as recorded in the audit. Other development packages still differ from release pins; this is fixture verification, not exact release reproduction.

**Environment limitation:** the final fixture suite passed, but `pip check` on the mixed test environment still failed (missing greenlet and MLflow constraints on pandas, pyarrow, cachetools, importlib-metadata and packaging). Do not use this mixed environment to approve or retrain a real release. The running Linux image independently passed its lock comparison and `pip check`. Full logs and exact versions are recorded in the sanitized validation JSON.
