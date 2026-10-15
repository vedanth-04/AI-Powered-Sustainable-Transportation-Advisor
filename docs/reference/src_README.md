# Source Code Directory (`src/`)

This directory contains the production-grade, modular Python codebase for the **AI-Powered Sustainable Transportation Advisor**.

## Package Layout Plan

As the project progresses through phases, code tested in notebooks will be refactored into the following modules:

```text
src/
├── __init__.py
├── README.md             <- This documentation
├── config.py             <- Global path definitions, random seed, and configuration constants
├── data/                 <- Data ingestion and quality auditing
│   ├── __init__.py
│   ├── loader.py         <- SQLite database connectors and batch extractors
│   └── quality_audit.py  <- Schema validation, timestamp verification, stale point filtering
├── features/             <- Label derivation and feature engineering
│   ├── __init__.py
│   ├── label_derivation.py <- Detection of segment boundary crossings and travel-time label computation
│   └── build_features.py   <- Temporal, spatial, and historical statistical feature generation
├── models/               <- Model training and evaluation
│   ├── __init__.py
│   ├── baseline.py       <- Historical-median baseline predictor
│   ├── train.py          <- Training pipelines for Random Forest & Gradient Boosting Regressors
│   └── evaluate.py       <- MAE, RMSE, and route/hour segment error analysis
└── utils/                <- Logging, metrics, and helper utilities
    ├── __init__.py
    └── logger.py         <- Structured logging setup
```

## Guidelines for Adding Code

1. **Modularity & Reusability:** Every script should have functions with clear input/output types and descriptive docstrings.
2. **Reproducibility:** Fix random seeds across all randomized algorithms (`random_state=42`).
3. **No Hardcoded Absolute Paths:** Use paths relative to the project root, managed through `config.py` or `pathlib.Path`.
4. **Testing:** Accompany each module with corresponding unit tests in `tests/`.
