"""Global configuration and path management for AI-Powered Sustainable Transportation Advisor."""

from __future__ import annotations

import os
from pathlib import Path

# Repository root path resolved dynamically
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data directory paths
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Default raw SQLite database file
DEFAULT_RAW_DB = RAW_DATA_DIR / "2019-07-01.db"

# Delhi geographic bounding envelope (used for noise/out-of-bounds rejection)
DELHI_LAT_MIN = 28.30
DELHI_LAT_MAX = 28.90
DELHI_LNG_MIN = 76.80
DELHI_LNG_MAX = 77.50

# Kinematic and data cleaning thresholds
MAX_IMPLIED_SPEED_KMH = 80.0  # Teleportation jump cutoff
NOMINAL_PING_INTERVAL_SEC = 10.0
MAX_TRAJECTORY_GAP_SEC = 300.0  # 5 min gap triggers trajectory segmentation
MAX_CROSSING_PING_GAP_SEC = 60.0  # Max gap allowed between pings straddling a gate line
MAX_WITHIN_SEGMENT_GAP_SEC = 180.0  # Max gap allowed inside a segment traversal

# Travel-time label validation bounds (in minutes)
MIN_TRAVEL_TIME_MINUTES = 1.0
MAX_TRAVEL_TIME_MINUTES = 45.0

# Reproducibility seed
RANDOM_SEED = 42

# MLflow Experiment and Model Registry constants
MLFLOW_EXPERIMENT_NAME = "BusTravelTime-ModelSelection"
MLFLOW_REGISTERED_MODEL_NAME = "BusTravelTimePredictor"
