# Team Contribution & Development Guide

Welcome to the **AI-Powered Sustainable Transportation Advisor** project!  
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
- **Python:** Python 3.12.5 (verify with `python --version`)
- **Git:** Git for Windows (verify with `git --version`)
- **Editor:** Visual Studio Code with the Python & Jupyter extensions installed

> **PowerShell Script Execution Policy:**  
> If PowerShell blocks activating your virtual environment with an execution policy error, run this command once in your PowerShell terminal:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

---

### Step 2.2: Clone the Repository
Clone the repository from GitHub into your local folder:
```powershell
git clone <GITHUB_REPOSITORY_URL>
cd ML-OPS-EL
```
*(Ask the project lead for the exact remote repository URL if you do not have it).*

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

## 3. Everyday Collaboration Workflow

Follow this cycle every time you work on a task to prevent merge conflicts and keep our Git history clean.

```text
[main branch] -> git pull -> git checkout -b feature/xyz -> write code/tests -> git commit -> git push -> GitHub Pull Request -> Review & Merge
```

### Step 3.1: Start from the Latest `main` Branch
Before starting new work, ensure your local copy has the latest changes:
```powershell
git checkout main
git pull origin main
```

---

### Step 3.2: Create a Dedicated Feature Branch
Never make commits directly on `main`. Create a descriptive branch named after your task:
```powershell
# Format: feature/<short-description> or fix/<short-description>
git checkout -b feature/schema-audit-sample
```

---

### Step 3.3: Make Changes & Test
- Write code in `src/`, notebooks in `notebooks/`, or documentation in `docs/`.
- If modifying notebooks, **clear all output cells** before saving (`Kernel -> Clear All Outputs`).
- Run tests to ensure nothing is broken:
  ```powershell
  pytest
  ```

---

### Step 3.4: Check Git Status & Stage Changes
Check what files were modified:
```powershell
git status
```

Stage only the files you intentionally modified:
```powershell
# Good practice: stage specific files
git add src/data/loader.py tests/test_data_loader.py

# Avoid: "git add ." if untracked temporary files are present
```

---

### Step 3.5: Commit with Meaningful Messages
Write a clear commit message explaining the change:
```powershell
# Examples:
git commit -m "feat(data): add SQLite batch query loader with context manager"
git commit -m "docs: document timestamp timezone audit procedure in docs/README.md"
git commit -m "fix(features): correct boundary crossing interpolation calculation"
```

---

### Step 3.6: Push Feature Branch to GitHub
Push your branch to GitHub:
```powershell
git push -u origin feature/schema-audit-sample
```

---

### Step 3.7: Open a Pull Request (PR)
1. Go to the project repository page on GitHub.
2. Click **"Compare & pull request"**.
3. Fill out the PR summary:
   - What changed?
   - What problem does it solve?
   - How was it verified?
4. Request a review from a teammate. Once approved, merge using **"Squash and merge"** or **"Rebase and merge"** to keep commit history clean.

---

## 4. Working with DVC (Data Version Control)

### Why DVC?
Git is designed for code and text files, not multi-gigabyte datasets. Storing large SQLite databases or model files in Git causes repositories to balloon in size and slows down cloning.

- **DVC solves this:** DVC stores the large files separately (local cache or remote cloud storage) and creates tiny `.dvc` text pointer files (hashes).
- **Rule:** You commit `.dvc` pointer files and `dvc.yaml` to Git. You **never** commit raw data files.

### Basic DVC Commands (Reference for upcoming phases)
```powershell
# Track a raw data file using DVC
dvc add data/raw/sample_2019_07_01.sqlite

# Git tracks the tiny .dvc pointer file created by DVC
git add data/raw/sample_2019_07_01.sqlite.dvc data/raw/.gitignore
git commit -m "chore(dvc): track July 1 sample SQLite database"
```

---

## 5. Working with MLflow (Experiment Tracking)

We use MLflow to track parameters, performance metrics, and model artifacts across every training run.

### Running MLflow in Code
In scripts or notebooks:
```python
import mlflow
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

mlflow.set_experiment("delhi_bus_travel_time_regression")

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
To launch the interactive dashboard:
```powershell
mlflow ui
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your web browser.  
> **Important:** The local tracking directory `mlruns/` is ignored in `.gitignore`. Do not attempt to force-add `mlruns/` to Git.

---

## 6. Common Git Issues & Resolutions on Windows

### 1. "Scripts are disabled on this system" when activating `.venv`
- **Cause:** Windows PowerShell restricted execution policy.
- **Fix:** In PowerShell, run:
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```

### 2. "Your local changes to the following files would be overwritten by checkout/pull"
- **Cause:** You have unsaved or uncommitted edits on your current branch.
- **Fix:** Either stash your changes or commit them:
  ```powershell
  git stash        # Temporarily shelve changes
  git pull origin main
  git stash pop    # Re-apply your changes
  ```

### 3. "fatal: refusing to merge unrelated histories"
- **Cause:** Local and remote repositories were initialized separately without a common root commit.
- **Fix:** Consult the team lead before forcing any merge. Typically resolved on first sync with:
  ```powershell
  git pull origin main --allow-unrelated-histories
  ```

### 4. Accidentally Staged a Large Data File or `.venv`
- **Cause:** Running `git add .` before verifying `.gitignore`.
- **Fix:** Unstage immediately:
  ```powershell
  git restore --staged <filename>
  ```
- If already committed locally (before pushing):
  ```powershell
  git reset --soft HEAD~1
  ```

### 5. "You are in 'detached HEAD' state"
- **Cause:** You checked out a specific commit hash rather than a branch name.
- **Fix:** Switch back to your branch:
  ```powershell
  git checkout main
  # or
  git checkout feature/your-branch-name
  ```

---

## 7. Security & Secrets Checklist

- **Never** commit passwords, API tokens, database connection strings with credentials, or personal keys.
- Store local configuration in `.env` files (which are ignored by `.gitignore`).
- If you accidentally commit a credential, notify the project lead immediately so the key can be rotated and the commit purged from history.
