# Notebooks Directory

This folder contains Jupyter notebooks used for exploratory data analysis (EDA), data audit investigations, feature exploration, and initial modeling prototypes.

## Notebook Conventions & Workflow

1. **Naming Standard:**
   - Use numbered prefixes indicating logical progression:
     - `01_dataset_schema_and_integrity_audit.ipynb` - Initial inspection of SQLite schemas, time stamps, timezones, missing values, duplicate records, and sampling gap audits.
     - `02_exploratory_data_analysis.ipynb` - Spatial distribution of GPS points, route exploration, speed and delay profiles.
     - `03_segment_boundary_label_derivation.ipynb` - Validating vehicle transit across segment boundaries to construct ground-truth segment travel times.
     - `04_feature_engineering_exploration.ipynb` - Feature generation (departure hour, day of week, segment distance, historical congestion statistics).
     - `05_baseline_and_tree_models.ipynb` - Prototype historical-median, Random Forest, and Gradient Boosting regressors with MLflow tracking.

2. **Clean Notebook Hygiene:**
   - Always **clear cell outputs** before committing notebooks to Git to avoid repository bloat and diff noise:
     In VS Code / Jupyter: `Kernel -> Restart Kernel and Clear All Outputs`.
   - Never hardcode absolute paths; use relative paths from the project root or use project path helpers.
   - Never store API keys, tokens, or personal identifiers in notebooks.

3. **Transition to Production Code:**
   - Notebooks are for experimentation and visualization.
   - Once data cleaning, label derivation, or feature engineering logic stabilizes, refactor the code into reusable functions and classes inside `src/`.
