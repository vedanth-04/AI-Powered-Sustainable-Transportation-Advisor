"""Create a synthetic Route 90 model bundle for the container smoke test."""

import argparse
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import joblib
import pandas as pd
from sklearn import __version__ as sklearn_version
from sklearn.compose import make_column_transformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeRegressor

from src.api.bundle import DEFAULT_BUNDLE_DIR, BundleManifest
from src.config import MLFLOW_REGISTERED_MODEL_NAME, RANDOM_SEED
from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, engineer_features
from src.features.segment_config import SEGMENT_ORR_EASTBOUND


def prepare_bundle(bundle_dir: Path) -> None:
    segment = SEGMENT_ORR_EASTBOUND
    entry_at = datetime.fromisoformat("2019-07-08T17:10:00+05:30")
    row = pd.DataFrame([{
        "segment_id": segment.segment_id,
        "direction": segment.direction,
        "route_id": "90",
        "segment_length_km": segment.length_km,
        "t_entry": entry_at.timestamp(),
    }])
    feature_columns = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    features = engineer_features(row, use_observed_history=False)[feature_columns]
    model = make_pipeline(
        make_column_transformer(
            (OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ("passthrough", NUMERIC_FEATURES),
        ),
        DecisionTreeRegressor(random_state=RANDOM_SEED),
    )
    model.fit(features, [6.25])

    serialized_model = BytesIO()
    joblib.dump(model, serialized_model)
    model_bytes = serialized_model.getvalue()
    manifest = BundleManifest(
        model_name=MLFLOW_REGISTERED_MODEL_NAME,
        model_version=1,
        history_policy="cold_start_v1",
        features=feature_columns,
        model_sha256=sha256(model_bytes).hexdigest(),
        scikit_learn_version=sklearn_version,
        segment_id=segment.segment_id,
        route_id="90",
    )
    manifest_json = manifest.model_dump_json(indent=2) + "\n"

    bundle_dir.mkdir(parents=True, exist_ok=False)
    model_path = bundle_dir / "model.joblib"
    manifest_path = bundle_dir / "manifest.json"
    try:
        model_path.write_bytes(model_bytes)
        manifest_path.write_text(manifest_json, encoding="utf-8")
    except OSError:
        manifest_path.unlink(missing_ok=True)
        model_path.unlink(missing_ok=True)
        bundle_dir.rmdir()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    args = parser.parse_args()
    try:
        prepare_bundle(args.bundle_dir)
    except FileExistsError:
        parser.error(f"Bundle directory already exists. Choose a new path: {args.bundle_dir}")
    print(f"Prepared a synthetic CI bundle at {args.bundle_dir.resolve()}")


if __name__ == "__main__":
    main()
