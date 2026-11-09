"""Exercise the Route 90 prediction API against a local model bundle."""

from datetime import datetime
from hashlib import sha256
import json

from fastapi.testclient import TestClient
import joblib
import pandas as pd
import pytest
import sklearn
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeRegressor

from src.api.main import create_app
from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, engineer_features
from src.features.segment_config import SEGMENT_ORR_EASTBOUND
from src.models.train import build_preprocessing_pipeline


FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
REQUEST = {
    "segment_id": SEGMENT_ORR_EASTBOUND.segment_id,
    "route_id": "90",
    "entry_at": "2019-07-08T08:10:00+05:30",
}


def cold_start_features(*entry_times):
    inputs = pd.DataFrame([
        {
            "segment_id": SEGMENT_ORR_EASTBOUND.segment_id,
            "direction": SEGMENT_ORR_EASTBOUND.direction,
            "route_id": REQUEST["route_id"],
            "segment_length_km": SEGMENT_ORR_EASTBOUND.length_km,
            "t_entry": datetime.fromisoformat(entry_at).timestamp(),
        }
        for entry_at in entry_times
    ])
    return engineer_features(inputs, use_observed_history=False)[FEATURE_COLUMNS]


@pytest.fixture
def model_bundle(tmp_path):
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    model = Pipeline([
        ("preprocessor", build_preprocessing_pipeline()),
        ("regressor", DecisionTreeRegressor(random_state=42)),
    ])
    model.fit(
        cold_start_features(REQUEST["entry_at"], "2019-07-08T17:10:00+05:30"),
        [5.0, 13.0],
    )
    model_path = bundle_dir / "model.joblib"
    joblib.dump(model, model_path)
    manifest = {
        "model_name": "BusTravelTimePredictor",
        "model_version": 1,
        "history_policy": "cold_start_v1",
        "features": FEATURE_COLUMNS,
        "model_sha256": sha256(model_path.read_bytes()).hexdigest(),
        "scikit_learn_version": sklearn.__version__,
        "segment_id": REQUEST["segment_id"],
        "route_id": REQUEST["route_id"],
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle_dir, model


def test_health_and_bus_prediction_match_offline_model(model_bundle):
    bundle_dir, model = model_bundle
    # The UTC representation of the evening training time must use its IST features.
    entry_times = [REQUEST["entry_at"], "2019-07-08T11:40:00+00:00"]
    expected_durations = model.predict(cold_start_features(*entry_times))
    assert expected_durations.tolist() == [5.0, 13.0]

    with TestClient(create_app(bundle_dir)) as client:
        health = client.get("/health")
        assert health.status_code == 200
        health_body = health.json()
        assert health_body["status"] == "ready"
        assert health_body["model_name"] == "BusTravelTimePredictor"
        assert health_body["model_version"] == 1
        assert health_body["history_policy"] == "cold_start_v1"

        for entry_at, expected in zip(entry_times, expected_durations):
            response = client.post("/predict/bus", json={**REQUEST, "entry_at": entry_at})
            assert response.status_code == 200
            body = response.json()
            assert body["duration_minutes"] == pytest.approx(expected)
            assert body["model_version"] == 1
            assert body["estimate_source"] == "model"
            assert body["history_policy"] == "cold_start_v1"


def test_hash_mismatch_makes_api_unready(model_bundle):
    bundle_dir, _ = model_bundle
    model_path = bundle_dir / "model.joblib"
    with model_path.open("ab") as stream:
        stream.write(b"artifact changed after publishing")

    with TestClient(create_app(bundle_dir)) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/predict/bus", json=REQUEST).status_code == 503


@pytest.mark.parametrize('failure', ['missing-model', 'missing-manifest', 'bad-json', 'wrong-runtime', 'wrong-schema', 'wrong-policy'])
def test_unusable_artifacts_fail_closed(model_bundle, failure):
    bundle_dir, _ = model_bundle
    path = bundle_dir / 'manifest.json'
    manifest = json.loads(path.read_bytes())
    if failure == 'missing-model':
        (bundle_dir / 'model.joblib').unlink()
    elif failure == 'missing-manifest':
        path.unlink()
    elif failure == 'bad-json':
        path.write_text('{bad json')
    else:
        key, value = {'wrong-runtime': ('scikit_learn_version', '0.0.0'),
                      'wrong-schema': ('features', ['unknown']),
                      'wrong-policy': ('history_policy', 'observed_history')}[failure]
        manifest[key] = value
        path.write_text(json.dumps(manifest))
    with TestClient(create_app(bundle_dir)) as client:
        assert client.get('/health').status_code == 503
        assert client.post('/predict/bus', json=REQUEST).status_code == 503


def test_trusted_manifest_pin_rejects_forgery_before_deserialization(model_bundle, monkeypatch):
    from src.api import bundle
    directory, _ = model_bundle
    trusted_digest = sha256((directory / 'manifest.json').read_bytes()).hexdigest()
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    manifest['model_version'] = 999
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(bundle.joblib, 'load', lambda *args: pytest.fail('Forged manifest reached joblib'))
    monkeypatch.setenv('BUS_MODEL_MANIFEST_SHA256', trusted_digest)
    with TestClient(create_app(directory)) as client:
        assert client.get('/health').status_code == 503


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"route_id": "83"}, id="unsupported-route"),
        pytest.param({"segment_id": "ORR_NEHRU_PLACE_TO_CHIRAG_WB"}, id="unsupported-segment"),
        pytest.param({"route_id": 90}, id="numeric-route"),
        pytest.param({"segment_id": 90}, id="numeric-segment"),
        pytest.param({"entry_at": "2019-07-08T08:10:00"}, id="naive-time"),
        pytest.param({"entry_at": 1562553600}, id="numeric-time"),
        pytest.param({"entry_at": "1562553600"}, id="numeric-string-time"),
        pytest.param({"travel_time_minutes": 10.0}, id="extra-target"),
    ],
)
def test_rejects_invalid_or_unsupported_requests(model_bundle, override):
    bundle_dir, _ = model_bundle

    with TestClient(create_app(bundle_dir)) as client:
        response = client.post("/predict/bus", json={**REQUEST, **override})

    assert response.status_code == 422


@pytest.mark.parametrize('value', [None, [], [1, 2], [[1]], ['bad'], [float('nan')], [float('inf')], [0], [-1]])
def test_invalid_prediction_results_are_controlled_503(model_bundle, monkeypatch, value):
    bundle_dir, _ = model_bundle
    with TestClient(create_app(bundle_dir)) as client:
        monkeypatch.setattr(client.app.state.bundle.model, 'predict', lambda frame: value)
        response = client.post('/predict/bus', json=REQUEST)
        assert response.status_code == 503
        assert client.get('/health').status_code == 200  # Loaded-model readiness contract unchanged.


def test_prediction_exception_and_logs_do_not_expose_sensitive_text(model_bundle, monkeypatch, caplog):
    import logging
    directory, _ = model_bundle
    with TestClient(create_app(directory)) as client, caplog.at_level(logging.INFO, logger='src.api.main'):
        def broken(frame):
            raise RuntimeError('credential=do-not-log-this')
        monkeypatch.setattr(client.app.state.bundle.model, 'predict', broken)
        response = client.post('/predict/bus?secret=hidden', json=REQUEST,
                               headers={'X-Request-ID': 'faculty-demo-1', 'Authorization': 'secret-header'})
    assert response.status_code == 503
    assert response.headers['x-request-id'] == 'faculty-demo-1'
    events = [json.loads(r.message) for r in caplog.records if r.name == 'src.api.main']
    failure = next(e for e in events if e['event'] == 'inference_failure')
    request = next(e for e in events if e['event'] == 'http_request')
    assert failure['request_id'] == request['request_id'] == 'faculty-demo-1'
    assert request['status'] == 503 and request['latency_ms'] >= 0
    assert request['model_version'] == 1 and request['history_policy'] == 'cold_start_v1'
    assert request['route_id'] == '90' and request['segment_id'] == REQUEST['segment_id']
    assert not any(secret in caplog.text for secret in ('do-not-log-this', 'secret-header', 'secret=hidden', REQUEST['entry_at']))


@pytest.mark.parametrize('payload', [{}, None, [], {'route_id': None}, {**REQUEST, 'entry_at': 'invalid'}, {**REQUEST, 'entry_at': '0001-01-01T00:00:00+00:00'}])
def test_malformed_requests_remain_422(model_bundle, payload):
    directory, _ = model_bundle
    with TestClient(create_app(directory)) as client:
        response = client.post('/predict/bus', content=json.dumps(payload), headers={'Content-Type': 'application/json'})
        assert response.status_code == 422
        assert response.headers['x-request-id']


def test_openapi_example_is_executable_and_invalid_request_id_is_replaced(model_bundle):
    directory, _ = model_bundle
    with TestClient(create_app(directory)) as client:
        assert client.get('/docs').status_code == 200
        example = client.get('/openapi.json').json()['components']['schemas']['BusPredictionRequest']['examples'][0]
        response = client.post('/predict/bus', json=example, headers={'X-Request-ID': 'untrusted ' * 30})
        assert response.status_code == 200
        assert len(response.headers['x-request-id']) == 32
