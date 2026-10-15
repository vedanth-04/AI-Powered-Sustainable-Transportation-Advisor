# Test Suite Directory (`tests/`)

This directory houses unit and integration tests to ensure data pipeline integrity, label calculation correctness, and model reproducibility.

## Running Tests

From the project root with the virtual environment activated:

```powershell
pytest
```

To run with verbose output:

```powershell
pytest -v
```

## Planned Test Modules

- `test_data_loader.py`: Verifies SQLite schema connection and safe batch extraction.
- `test_quality_audit.py`: Validates timestamp parsing, bounding-box coordinate filters, and duplicate rejection.
- `test_label_derivation.py`: Tests segment boundary crossing logic on synthetic trajectory fixtures to ensure travel times are calculated accurately and anomalous transit events are rejected.
- `test_baseline.py`: Tests that the historical-median baseline outputs expected median predictions for test inputs.
