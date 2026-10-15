# Team Onboarding & DVC Data Setup Guide

## 1. Overview & Architecture

In this project (**AI-Powered Sustainable Transportation Advisor**), code, configuration, documentation, and metadata pointer files are version-controlled with **Git**, while large raw data assets are tracked and managed using **Data Version Control (DVC)**.

- **Primary Repository (GitHub):** [AI-Powered-Sustainable-Transportation-Advisor](https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor)
- **Data Remote Storage (DagsHub):** [DagsHub Repository & S3-compatible Storage](https://dagshub.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor)
- **Dataset Tracked:** `data/raw/2019-07-01.db` (~184.46 MB SQLite database, 1,977,922 rows)
- **DVC Pointer File:** `data/raw/2019-07-01.db.dvc` (tracked in Git; points to MD5 hash `e3c31e6255359b7a4ebf93b3154659b2`)

> **IMPORTANT:** Running `git clone` downloads project source code and lightweight `.dvc` pointer files, but **does not download the dataset itself**. Every collaborator must follow the steps below to configure local authentication and pull the data from DagsHub.

---

## 2. Prerequisites

Before beginning, ensure you have the following installed and set up on your Windows system:

1. **Operating System:** Windows 10 or 11 with **PowerShell 5.1+** or **PowerShell 7+**.
2. **Git:** Installed and configured (`git --version`).
3. **Python:** Python 3.10+ (tested on Python 3.12, `python --version`).
4. **DagsHub Account & Access:**
   - Create a free account at [dagshub.com](https://dagshub.com) if you do not already have one.
   - Request collaborator access to the project repository: `https://dagshub.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor`.
5. **Personal DagsHub Access Token:**
   - Log in to DagsHub.
   - Go to **Your Profile Picture** (top-right) -> **Settings** -> **Tokens**.
   - Generate a personal access token (e.g., named `dvc-token`).
   - Copy this token securely. **Never share this token or commit it to Git.**

---

## 3. Step-by-Step Setup Instructions (Windows PowerShell)

Open **PowerShell** (run in your standard user directory or development workspace).

### Step 1: Clone the GitHub Repository

Clone the project repository to your local machine and navigate into the root directory:

```powershell
git clone https://github.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor.git
cd AI-Powered-Sustainable-Transportation-Advisor
```

---

### Step 2: Create and Activate a Virtual Environment

Isolate project dependencies by creating a dedicated Python virtual environment:

```powershell
# Create the virtual environment
python -m venv .venv

# Allow script execution for the current session if needed
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1
```

Once activated, your terminal prompt should display `(.venv)`.

---

### Step 3: Install Project Dependencies

Install project dependencies, including `dvc` and the `dvc-s3` storage plugin:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Verify that DVC is available and S3 support is active:

```powershell
.\.venv\Scripts\dvc.exe version
```

Confirm under **Supported remotes** that `s3 (s3fs = ...)` is listed.

---

### Step 4: Configure Secure Local Authentication

The repository comes pre-configured with a default remote named `teamstorage` pointing to DagsHub's S3 endpoint (`s3://dvc` at `https://dagshub.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor.s3`).

To authenticate without exposing credentials to Git or team members, save your personal token to **local DVC configuration** (`.dvc/config.local`). This file is strictly excluded by `.gitignore`.

Run the following commands in PowerShell. When prompted, paste your DagsHub personal access token:

```powershell
# Securely capture your DagsHub token into a variable
$dagshubToken = Read-Host -Prompt "Enter your DagsHub Personal Access Token" -AsSecureString
$tokenPlain = [System.Net.NetworkCredential]::new("", $dagshubToken).Password

# Configure DVC S3 credentials locally (both access key and secret key take the token)
.\.venv\Scripts\dvc.exe remote modify teamstorage --local access_key_id $tokenPlain
.\.venv\Scripts\dvc.exe remote modify teamstorage --local secret_access_key $tokenPlain

# Clear the variable from PowerShell memory
Remove-Variable tokenPlain, dagshubToken
```

#### Confirm Configuration & Git Hygiene

Verify that authentication settings exist locally without printing the token value:

```powershell
# Safely verify credentials exist and are non-empty without printing token values
$hasAccess = (Select-String -Path .dvc\config.local -Pattern "access_key_id\s*=\s*\S+" -Quiet)
$hasSecret = (Select-String -Path .dvc\config.local -Pattern "secret_access_key\s*=\s*\S+" -Quiet)
Write-Host "Credentials configured: access_key_id=$hasAccess, secret_access_key=$hasSecret"

# Confirm .dvc/config.local is ignored by Git
git check-ignore -v .dvc/config.local
# Expected output: .gitignore:106:.dvc/config.local

# Confirm working tree has no staged credentials
git status --short
```

---

### Step 5: Pull the Dataset from DagsHub

Download the raw database using DVC:

```powershell
.\.venv\Scripts\dvc.exe pull data/raw/2019-07-01.db.dvc -r teamstorage
```

*Note: The download size is approximately 184.5 MB. Depending on your internet connection, this may take between 30 seconds and a few minutes.*

When the pull completes, you will see output confirming:
```text
A       data\raw\2019-07-01.db
1 file fetched
```

---

### Step 6: Verify Dataset Integrity

Confirm that the downloaded SQLite database is present, matches expected file dimensions, and passes SQLite integrity checks:

```powershell
# 1. Verify file size (must equal exactly 193,421,312 bytes)
(Get-Item data\raw\2019-07-01.db).Length

# 2. Verify MD5 hash (must match e3c31e6255359b7a4ebf93b3154659b2)
(Get-FileHash -Algorithm MD5 data\raw\2019-07-01.db).Hash.ToLower()

# 3. Verify SQLite integrity and row count
.\.venv\Scripts\python.exe -c "import sqlite3; con = sqlite3.connect('data/raw/2019-07-01.db'); print('Integrity:', con.execute('PRAGMA integrity_check;').fetchone()[0]); print('Row count:', con.execute('SELECT COUNT(*) FROM vehicle_feed;').fetchone()[0]); con.close()"
```

**Expected Results:**
- **Length:** `193421312`
- **MD5 Hash:** `e3c31e6255359b7a4ebf93b3154659b2`
- **Integrity:** `ok`
- **Row count:** `1977922`

---

## 4. Security Rules & Hygiene

1. **Never Commit Credentials:**
   - Never add access keys, tokens, or passwords to `.dvc/config`, scripts, notebooks, or documentation.
   - Always pass the `--local` flag to `dvc remote modify` commands to write to `.dvc/config.local`.
2. **Never Commit SQLite Databases (`*.db`):**
   - The raw database `data/raw/2019-07-01.db` and any derived SQLite databases are ignored by `.gitignore`.
   - Only commit `.dvc` pointer files (e.g., `data/raw/2019-07-01.db.dvc`).
3. **Token Revocation:**
   - If you suspect your DagsHub token has been exposed or compromised, immediately revoke it via **DagsHub -> Settings -> Tokens** and generate a new one.

---

## 5. Troubleshooting & FAQ

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| **`AccessDenied (403 Forbidden)`** | Invalid DagsHub token or missing collaborator permission on DagsHub repo | Verify you were added as a collaborator to the DagsHub repository. Re-enter your token in `.dvc/config.local`. |
| **`The term 'dvc' is not recognized`** | Virtual environment is not activated or DVC is not in PATH | Run `.\.venv\Scripts\Activate.ps1` or invoke `.\.venv\Scripts\dvc.exe` directly. |
| **`Execution of scripts is disabled on this system`** | Windows PowerShell execution policy restriction | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` in your PowerShell session. |
| **`unsupported remote type 's3'`** | `dvc-s3` plugin is missing in virtual environment | Run `.\.venv\Scripts\python.exe -m pip install "dvc-s3>=3.2.0"`. |
| **`dvc pull` reports `Everything is up to date` but file is missing** | Specific pointer file was not targeted | Explicitly specify the target: `.\.venv\Scripts\dvc.exe pull data/raw/2019-07-01.db.dvc -r teamstorage`. |
