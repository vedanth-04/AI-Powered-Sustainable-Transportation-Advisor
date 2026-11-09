"""FastAPI endpoints for the historical bus travel-time demo."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import logging
from math import isfinite
import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictStr, field_validator

from src.api.bundle import DEFAULT_BUNDLE_DIR, ServingBundle, load_bundle
from src.features.build_features import engineer_features

logger = logging.getLogger(__name__)


class BusPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: StrictStr
    route_id: StrictStr
    entry_at: AwareDatetime

    @field_validator("entry_at", mode="before")
    @classmethod
    def parse_entry_time(cls, value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("entry_at must be an ISO 8601 timestamp with a timezone offset.")
        return datetime.fromisoformat(value)


class HealthResponse(BaseModel):
    status: Literal["ready"] = "ready"
    model_name: str
    model_version: int
    history_policy: str


class PredictionResponse(BaseModel):
    duration_minutes: float
    model_version: int
    estimate_source: Literal["model"] = "model"
    history_policy: str


def require_model(request: Request) -> ServingBundle:
    bundle = getattr(request.app.state, "bundle", None)
    if bundle is None:
        raise HTTPException(status_code=503, detail="The prediction model is unavailable.")
    return bundle


def create_app(bundle_dir: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        path = bundle_dir or Path(os.environ.get("BUS_MODEL_BUNDLE_DIR", str(DEFAULT_BUNDLE_DIR)))
        try:
            application.state.bundle = load_bundle(path, expected_manifest_sha256=os.environ.get('BUS_MODEL_MANIFEST_SHA256'))
        except Exception:
            # Keep readiness available to report a bundle load failure.
            logger.exception("Could not load the serving bundle at %s", path)
            application.state.bundle = None
        yield

    application = FastAPI(
        title="Bus Travel-Time Predictor",
        description="Historical demo for the approved bus route and road segment.",
        lifespan=lifespan,
    )

    @application.get("/health", responses={503: {"description": "Model unavailable"}})
    def health(bundle: ServingBundle = Depends(require_model)) -> HealthResponse:
        return HealthResponse(
            model_name=bundle.manifest.model_name,
            model_version=bundle.manifest.model_version,
            history_policy=bundle.manifest.history_policy,
        )

    @application.post("/predict/bus", responses={503: {"description": "Model unavailable"}})
    def predict_bus(
        trip: BusPredictionRequest, bundle: ServingBundle = Depends(require_model)
    ) -> PredictionResponse:
        manifest = bundle.manifest
        if (trip.segment_id, trip.route_id) != (manifest.segment_id, manifest.route_id):
            raise HTTPException(status_code=422, detail="This route and segment are outside the approved demo scope.")
        try:
            entry = pd.DataFrame([{
                "segment_id": bundle.segment.segment_id,
                "direction": bundle.segment.direction,
                "segment_length_km": bundle.segment.length_km,
                "route_id": manifest.route_id,
                "t_entry": trip.entry_at.timestamp(),
            }])
            features = engineer_features(entry, use_observed_history=False)[manifest.features]
        except (ValueError, OverflowError, OSError) as exc:
            raise HTTPException(status_code=422, detail="entry_at is outside the supported time range.") from exc
        duration = float(bundle.model.predict(features)[0])
        if not isfinite(duration) or duration <= 0:
            raise HTTPException(status_code=503, detail="The model did not return a valid duration.")
        return PredictionResponse(
            duration_minutes=duration,
            model_version=manifest.model_version,
            history_policy=manifest.history_policy,
        )

    return application


app = create_app()
