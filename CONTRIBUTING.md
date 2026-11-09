# Team Contribution & Development Guide

Welcome to the **AI-Powered Sustainable Transportation Advisor** project!<br>
This guide is written specifically for team members and collaborators working on **Windows with PowerShell**, including those new to Git, DVC, or MLflow.

---

## 1. Project Overview & Target

- **Goal:** Predict bus-segment travel times in minutes using real-world Delhi bus GPS observations.
- **Target Variable:** Continuous travel time (minutes) for a transit bus traversing a specific road segment.
- **Why It Matters:** Enables accurate arrival estimations and reliable journey recommendations for sustainable urban transport.
- **Important Note:** Raw GPS pings are not travel times! We derive travel times by validating journeys across defined segment boundary lines.

---

## 2. One-Time Setup (New Collaborators)

Complete these steps once when setting up your development machine.

### Step 2.1: Prerequisites
- **Operating System:** Windows 10/11
- **Shell:** Windows PowerShell
- **Python:** Python 3.12 (record the actual patch version; verify with `python --version`)
- **Git:** Git for Windows (verify with `git --version`)
- **Editor:** Visual Studio Code with the Python & Jupyter extensions installed

> **PowerShell Script Execution Policy:**<br>
> If PowerShell blocks activating your virtual environment with an execution policy error, run this command once in your PowerShell terminal:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
> ```

---

### Step 2.2: Clone the Repository
Clone the repository from GitHub into your local folder:
```powershell
git clone https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor.git
cd AI-Powered-Sustainable-Transportation-Advisor
```
For inference only, follow the [published-image demo](docs/phase2_demo.md); no host training environment or raw dataset is needed.

---

### Step 2.3: Create and Activate the Virtual Environment
Create a dedicated virtual environment named `.venv` using Python 3.12:
```powershell
# Create .venv
python -m venv .venv

# Activate .venv in PowerShell
.\.venv\Scripts\Activate.ps1
```
When activated, you will see `(.venv)` at the beginning of your PowerShell prompt line.

---

### Step 2.4: Install Project Dependencies
Upgrade pip and install all required packages:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 2.5: Obtain the Dataset Separately
The raw dataset is approximately **1.8 GB** and is **never** committed directly to Git.

1. Download the July 2019 Delhi Bus GPS archive from Zenodo:
   - **Download Link:** [Zenodo July 19 Corrected Archive](https://zenodo.org/records/21738157/files/july_19_corrected.zip?download=1)
2. Place the downloaded archive into `data/raw/`:
   ```text
   ML-OPS-EL/data/raw/july_19_corrected.zip
   ```
3. Extract only the representative sample database designated by the project lead for Phase 2 exploration into `data/raw/`.
4. **Notice:** `.gitignore` automatically blocks `.zip` and `.sqlite` files inside `data/raw/` from being added to Git.

---

## 3. Direct collaboration on main

The team currently commits directly to `main`. No new feature branch or pull request is required. Earlier commits used PRs; those remain part of the historical record.

Start from a clean checkout and inspect remote changes:

```powershell
git status --short --branch
git branch --show-current
git fetch origin
git rev-list --left-right --count HEAD...origin/main
```

On `main`, `0 N` means a fast-forward is possible. With a clean working tree and no incoming-file collisions, run `git merge --ff-only origin/main`. If there are local edits, inspect and preserve them before integrating. Never reset, clean or force-push to solve a synchronization problem.

Make a meaningful change, run the relevant checks and review the full diff. Stage named files only. Keep notebook outputs that provide useful historical evidence unless a separate edit is intended; do not regenerate notebooks merely to clear them.

```powershell
git diff --check
git diff
# Replace this example path with the intentional files for the current change.
git add README.md
git diff --cached --stat
git diff --cached
```

Before committing, fetch again and verify the remote has not advanced. After committing, fetch immediately before **every push**:

```powershell
git commit -m "docs: describe verified project progress"
git fetch origin
git rev-list --left-right --count HEAD...origin/main
git merge-base --is-ancestor origin/main HEAD
# Only after the ancestor check succeeds (exit code 0):
git push origin main
```

If both ahead and behind counts are nonzero, inspect the incoming commits. Integrate only after a conflict-free result is established; stop and report any conflict rather than choosing a side or discarding work. A normal push rejects a concurrent remote update; fetch and inspect again instead of forcing it.

---

## 4. Working with DVC (Data Version Control)

### Why DVC?
Git is designed for code and text files, not multi-gigabyte datasets. Storing large SQLite databases or model files in Git causes repositories to balloon in size and slows down cloning.

- **DVC solves this:** DVC stores the large files separately (local cache or remote cloud storage) and creates tiny `.dvc` text pointer files (hashes).
- **Rule:** You commit `.dvc` pointer files and `dvc.yaml` to Git. You **never** commit raw data files.

### Existing tracked sample
```powershell
# With local DagsHub credentials already configured:
.\.venv\Scripts\dvc.exe pull data/raw/2019-07-01.db.dvc -r teamstorage
Get-FileHash data/raw/2019-07-01.db -Algorithm MD5
```

Expected MD5: `e3c31e6255359b7a4ebf93b3154659b2`. The [DVC team guide](docs/reference/dvc_team_setup.md) explains local authentication. Only the July 1 raw database has a committed pointer; a versioned multi-day processed training dataset and a `dvc.yaml` pipeline are not present.

---

## 5. Working with MLflow (Experiment Tracking)

We use MLflow to track parameters, performance metrics, and model artifacts across every training run.

### Conceptual MLflow example (not a complete runnable training script)
In scripts or notebooks:
```python
import mlflow
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

mlflow.set_experiment("BusTravelTime-ModelSelection")

with mlflow.start_run(run_name="rf_baseline_v1"):
    # Log parameters
    mlflow.log_param("model_type", "RandomForestRegressor")
    mlflow.log_param("n_estimators", 100)
    mlflow.log_param("max_depth", 10)

    # Train model
    model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
    model.fit(X_train, y_train)

    # Evaluate
    preds = model.predict(X_val)
    mae = mean_absolute_error(y_val, preds)
    rmse = root_mean_squared_error(y_val, preds)

    # Log metrics
    mlflow.log_metric("mae_minutes", mae)
    mlflow.log_metric("rmse_minutes", rmse)
```

### Viewing the MLflow UI Locally
The batch experiment is `BusTravelTime-ModelSelection`; checked Phase 2 training uses `BusTravelTime-ColdStart`. To inspect an existing default store:
```powershell
mlflow ui
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your web browser.<br>
The original approved registry is a separate local SQLite store. Use the [registry instructions](docs/phase2_demo.md#6-open-the-correct-mlflow-registry) only when that database/artifact store exists. A blank default UI does not prove the approved model is missing. For model reproduction, use a new output directory and explicit authorization; never overwrite the approved release.

> **Important:** The local tracking directory `mlruns/` is ignored in `.gitignore`. Do not attempt to force-add `mlruns/` to Git.

---

## 6. Common Git Issues & Resolutions on Windows

### 1. "Scripts are disabled on this system" when activating `.venv`
- **Cause:** Windows PowerShell restricted execution policy.
- **Fix:** In PowerShell, run:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
  ```

### 2. Local changes block synchronization

Run `git status` and inspect the affected files. Preserve them and stop if integration is ambiguous. Do not automatically stash, reset or overwrite someone else's work.

### 3. Unrelated histories or conflicts

Stop and ask the team to reconcile repository history. Do not use `--allow-unrelated-histories` as a routine setup command.

### 4. Accidentally Staged a Large Data File or `.venv`
- **Cause:** Running `git add .` before verifying `.gitignore`.
- **Fix:** Unstage immediately:
  ```powershell
  git restore --staged path/to/file
  ```
- If already committed, stop before pushing and agree on the corrective commit/history procedure with the team.

### 5. "You are in 'detached HEAD' state"
- **Cause:** You checked out a specific commit hash rather than a branch name.
- **Fix:** Switch back to your branch:
  ```powershell
  git checkout main
  ```

---

## 7. Security & Secrets Checklist

- **Never** commit passwords, API tokens, database connection strings with credentials, or personal keys.
- Store local configuration in `.env` files (which are ignored by `.gitignore`).
- If you accidentally commit a credential, notify the project lead immediately so the key can be rotated and the commit purged from history.
