"""Load the pinned, trusted serving bundle without a registry connection."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Literal

import joblib
from pydantic import BaseModel, ConfigDict, Field, PositiveInt
from sklearn import __version__ as sklearn_version
from sklearn.base import BaseEstimator

from src.config import MLFLOW_REGISTERED_MODEL_NAME, OUTPUTS_DIR
from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from src.features.segment_config import RoadSegment, get_segment

DEFAULT_BUNDLE_DIR = OUTPUTS_DIR / "phase2_serving"


class BundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model_name: str
    model_version: PositiveInt
    history_policy: Literal["cold_start_v1"]
    features: list[str]
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scikit_learn_version: str
    segment_id: str
    route_id: str


@dataclass(frozen=True)
class ServingBundle:
    manifest: BundleManifest
    model: BaseEstimator
    segment: RoadSegment


def load_bundle(bundle_dir: Path) -> ServingBundle:
    manifest = BundleManifest.model_validate_json((bundle_dir / "manifest.json").read_bytes())
    if manifest.model_name != MLFLOW_REGISTERED_MODEL_NAME:
        raise ValueError("Unexpected model name in serving manifest.")
    if manifest.features != CATEGORICAL_FEATURES + NUMERIC_FEATURES:
        raise ValueError("Serving manifest feature schema does not match the application.")
    if manifest.scikit_learn_version != sklearn_version:
        raise ValueError("The artifact requires a different scikit-learn version.")
    segment = get_segment(manifest.segment_id)
    if manifest.route_id not in segment.primary_routes:
        raise ValueError("The approved route does not match the segment catalog.")

    model_bytes = (bundle_dir / "model.joblib").read_bytes()
    if sha256(model_bytes).hexdigest() != manifest.model_sha256:
        raise ValueError("Serving artifact checksum does not match the manifest.")
    model = joblib.load(BytesIO(model_bytes))
    if not callable(getattr(model, "predict", None)):
        raise ValueError("Serving artifact does not provide a predict method.")
    if list(getattr(model, "feature_names_in_", ())) != manifest.features:
        raise ValueError("Fitted model feature schema does not match the manifest.")
    return ServingBundle(manifest, model, segment)
