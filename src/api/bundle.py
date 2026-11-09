"""Load the pinned, trusted serving bundle without a registry connection."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal
from importlib.metadata import version
import json

import joblib
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator
from sklearn import __version__ as sklearn_version
from sklearn.base import BaseEstimator

from src.config import MLFLOW_REGISTERED_MODEL_NAME, OUTPUTS_DIR
from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from src.features.segment_config import RoadSegment, get_segment

DEFAULT_BUNDLE_DIR = OUTPUTS_DIR / "phase2_serving"

Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


def feature_schema_sha256() -> str:
    schema = {'categorical': CATEGORICAL_FEATURES, 'numeric': NUMERIC_FEATURES,
              'history_policy': 'cold_start_v1', 'route_dtype': 'string', 'schema_version': 1}
    return sha256(json.dumps(schema, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class DataIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['dvc', 'sha256_only']
    input_sha256: Hash
    raw_dvc_md5: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    raw_sha256: Hash | None = None
    pointer_sha256: Hash | None = None
    lineage_sha256: Hash | None = None
    dvc_lock_sha256: Hash | None = None

    @model_validator(mode='after')
    def require_dvc_identity(self):
        fields = (self.raw_dvc_md5, self.raw_sha256, self.pointer_sha256,
                  self.lineage_sha256, self.dvc_lock_sha256)
        if self.kind == 'dvc' and not all(fields):
            raise ValueError('DVC lineage is incomplete.')
        if self.kind == 'sha256_only' and any(fields):
            raise ValueError('Unversioned data cannot claim DVC provenance.')
        return self


class ReleaseProvenance(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    training_run_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    source_git_sha: str = Field(pattern=r'^[0-9a-f]{40}$')
    source_worktree_dirty: bool
    source_sha256: dict[str, Hash] = Field(min_length=1)
    data: DataIdentity
    feature_schema_sha256: Hash
    dependency_lock_sha256: Hash
    quality_report_sha256: Hash
    run_report_sha256: Hash
    model_runtime: dict[str, str]
    release_eligible: bool


class BundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    manifest_version: Literal[1, 2] = 1
    provenance: ReleaseProvenance | None = None

    model_name: str
    model_version: PositiveInt
    history_policy: Literal["cold_start_v1"]
    features: list[str]
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scikit_learn_version: str
    segment_id: str
    route_id: str

    @model_validator(mode='after')
    def require_versioned_provenance(self):
        if (self.manifest_version == 2) != (self.provenance is not None):
            raise ValueError('Only manifest v2 requires release provenance.')
        if self.provenance and self.provenance.release_eligible != (self.provenance.data.kind == 'dvc' and not self.provenance.source_worktree_dirty):
            raise ValueError('Release eligibility requires DVC lineage and a clean source snapshot.')
        return self


@dataclass(frozen=True)
class ServingBundle:
    manifest: BundleManifest
    model: BaseEstimator
    segment: RoadSegment


def load_bundle(bundle_dir: Path, *, expected_manifest_sha256: str | None = None) -> ServingBundle:
    manifest_bytes = (bundle_dir / 'manifest.json').read_bytes()
    # The optional digest comes from a trusted deployment record, never from this manifest.
    if expected_manifest_sha256 is not None and sha256(manifest_bytes).hexdigest() != expected_manifest_sha256:
        raise ValueError('Manifest differs from the trusted deployment digest.')
    manifest = BundleManifest.model_validate_json(manifest_bytes)
    if manifest.model_name != MLFLOW_REGISTERED_MODEL_NAME:
        raise ValueError("Unexpected model name in serving manifest.")
    if manifest.features != CATEGORICAL_FEATURES + NUMERIC_FEATURES:
        raise ValueError("Serving manifest feature schema does not match the application.")
    if manifest.scikit_learn_version != sklearn_version:
        raise ValueError("The artifact requires a different scikit-learn version.")
    if manifest.provenance:
        provenance = manifest.provenance
        if provenance.feature_schema_sha256 != feature_schema_sha256():
            raise ValueError('Versioned feature schema differs from the application.')
        names = {'scikit-learn', 'numpy', 'pandas', 'scipy', 'joblib'}
        if set(provenance.model_runtime) != names or any(version(name) != provenance.model_runtime[name] for name in names):
            raise ValueError('Versioned artifact runtime is incompatible.')
        if sha256((bundle_dir / 'environment.lock.txt').read_bytes()).hexdigest() != provenance.dependency_lock_sha256:
            raise ValueError('Bundled environment lock differs from approval.')
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
