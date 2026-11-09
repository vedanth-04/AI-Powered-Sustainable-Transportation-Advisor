"""FastAPI endpoints for the historical bus travel-time demo."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import logging
import json
from math import isfinite
import os
from pathlib import Path
import re
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
import pandas as pd
import numpy as np
from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictStr, field_validator

from src.api.bundle import DEFAULT_BUNDLE_DIR, ServingBundle, load_bundle
from src.features.build_features import engineer_features

logger = logging.getLogger(__name__)
EXAMPLE = {"segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB", "route_id": "90",
           "entry_at": "2019-07-08T17:10:00+05:30"}


def log_event(level: int, event: str, **fields) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, allow_nan=False))


class BusPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [EXAMPLE]})

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
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        path = bundle_dir or Path(os.environ.get("BUS_MODEL_BUNDLE_DIR", str(DEFAULT_BUNDLE_DIR)))
        try:
            application.state.bundle = load_bundle(path, expected_manifest_sha256=os.environ.get('BUS_MODEL_MANIFEST_SHA256'))
            log_event(logging.INFO, 'model_readiness', ready=True,
                      model_version=application.state.bundle.manifest.model_version,
                      history_policy=application.state.bundle.manifest.history_policy)
        except Exception as exc:
            # Keep readiness available to report a bundle load failure.
            log_event(logging.ERROR, 'model_readiness', ready=False, error_type=type(exc).__name__)
            application.state.bundle = None
        yield

    application = FastAPI(
        title="Bus Travel-Time Predictor",
        description="Historical demo for the approved bus route and road segment.",
        lifespan=lifespan,
    )

    @application.middleware('http')
    async def request_log(request: Request, call_next):
        supplied = request.headers.get('x-request-id', '')
        request_id = supplied if re.fullmatch(r'[A-Za-z0-9._-]{1,64}', supplied) else uuid4().hex
        request.state.request_id = request_id
        started = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers['X-Request-ID'] = request_id
            return response
        finally:
            bundle = getattr(application.state, 'bundle', None)
            manifest = bundle.manifest if bundle else None
            # Deliberately omit body, timestamps, headers, query strings and exception text.
            log_event(logging.INFO if status < 500 else logging.ERROR, 'http_request',
                      request_id=request_id, method=request.method,
                      path=request.scope.get('route').path if request.scope.get('route') else 'unmatched',
                      status=status, latency_ms=round((perf_counter() - started) * 1000, 3),
                      model_name=manifest.model_name if manifest else None,
                      model_version=manifest.model_version if manifest else None,
                      history_policy=manifest.history_policy if manifest else None,
                      **getattr(request.state, 'approved_scope', {}))

    @application.get("/health", responses={503: {"description": "Model unavailable"}})
    def health(bundle: ServingBundle = Depends(require_model)) -> HealthResponse:
        return HealthResponse(
            model_name=bundle.manifest.model_name,
            model_version=bundle.manifest.model_version,
            history_policy=bundle.manifest.history_policy,
        )

    @application.post("/predict/bus", responses={503: {"description": "Model unavailable"}})
    def predict_bus(
        trip: BusPredictionRequest, request: Request, bundle: ServingBundle = Depends(require_model)
    ) -> PredictionResponse:
        manifest = bundle.manifest
        if (trip.segment_id, trip.route_id) != (manifest.segment_id, manifest.route_id):
            raise HTTPException(status_code=422, detail="This route and segment are outside the approved demo scope.")
        request.state.approved_scope = {'route_id': manifest.route_id, 'segment_id': manifest.segment_id}
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
        except Exception as exc:
            log_event(logging.ERROR, 'inference_failure', request_id=request.state.request_id,
                      error_type=type(exc).__name__, model_version=manifest.model_version)
            raise HTTPException(status_code=503, detail='The prediction model is unavailable.') from exc
        try:
            values = np.asarray(bundle.model.predict(features), dtype=float)
            if values.shape != (1,):
                raise ValueError('Invalid prediction shape')
            duration = float(values[0])
            if not isfinite(duration) or duration <= 0:
                raise ValueError('Invalid duration')
        except Exception as exc:
            log_event(logging.ERROR, 'inference_failure', request_id=request.state.request_id,
                      error_type=type(exc).__name__, model_version=manifest.model_version)
            raise HTTPException(status_code=503, detail='The model did not return a valid duration.') from exc
        return PredictionResponse(
            duration_minutes=duration,
            model_version=manifest.model_version,
            history_policy=manifest.history_policy,
        )

    return application


app = create_app()
