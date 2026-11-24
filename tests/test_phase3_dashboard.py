"""Dashboard API payloads and server (the React app itself is built and checked separately)."""

import json

import pandas as pd
import pytest

from dashboard import data as D
from dashboard import payloads as P
from src.monitoring.replay import load_policy, load_splits, reproduce_v1, run_replay
from src.versioning.lifecycle import run_lifecycle
from tests.phase3_fixtures import fast_policy, synthetic_traversals


@pytest.fixture(scope="module")
def phase3_run(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("phase3")
    traversals = synthetic_traversals(slow_last_day=1.35)
    path = tmp_path / "traversals.csv"
    traversals.to_csv(path, index=False)
    policy_path = fast_policy(tmp_path)
    policy = load_policy(policy_path)
    splits = load_splits(path, policy)
    handle = reproduce_v1(splits[0])
    monitoring = run_replay(path, handle, tmp_path / "phase3" / "monitoring", policy_path=policy_path, splits=splits)
    run_lifecycle(traversals=pd.concat(splits), traversals_sha256=None, output_dir=tmp_path / "phase3", v1=handle,
                  v1_bytes=None, v1_training=splits[0], monitoring_report=monitoring, monitoring_policy=policy,
                  actor="tester", mlflow_sync=False)
    return tmp_path / "phase3"


def _strict(payload) -> dict:
    return json.loads(json.dumps(payload, allow_nan=False))  # the browser needs strict JSON (no NaN)


def test_payloads_tolerate_missing_artifacts(tmp_path):
    state = _strict(P.build_state(phase3_dir=tmp_path / "nothing-here"))
    assert state["monitoring"] is None and state["registry"] is None
    assert len(state["pipeline"]) == 11 and state["kpis"]["champion"] is None
    assert P.build_scenario(tmp_path / "nothing-here", "natural") is None
    assert P.build_scenario(tmp_path, "not-a-scenario") is None


def test_state_and_scenarios_feed_every_page(phase3_run):
    state = _strict(P.build_state(phase3_dir=phase3_run))
    assert state["kpis"]["champion"] >= 1 and state["kpis"]["chain_valid"] is True
    registry = state["registry"]
    assert [v["version"] for v in registry["versions"]][:1] == [1]
    assert "1-2" in registry["diffs"] and registry["holdout_rolling"]
    assert any(stage["tools"] for stage in state["pipeline"])
    assert all(set(control) == {"area", "control", "passed", "evidence"} for control in state["governance"]["controls"])
    assert {s["name"] for s in state["monitoring"]["scenarios"]} == set(D.SCENARIOS)
    for name in D.SCENARIOS:
        scenario = _strict(P.build_scenario(phase3_run, name))
        assert scenario["timeline"] and len(scenario["timeline"][0]) == 6
        assert scenario["detectors"][0]["name"] == "all_segments" and scenario["detectors"][0]["points"]
        assert all(set(w["statuses"]) == {"Input drift", "Prediction drift", "Data quality", "Performance"}
                   for w in scenario["windows"])
    concept = P.build_scenario(phase3_run, "concept_drift")
    assert concept["markers"]["onset"] is not None


def test_predictions_and_probe_guard(phase3_run):
    result = _strict(P.predict_all(phase3_run, "ORR_CHIRAG_TO_NEHRU_PLACE_EB", "2019-07-08", "17:10"))
    assert result["in_api_scope"] and len(result["predictions"]) >= 2
    assert all(p["minutes"] is None or p["minutes"] > 0 for p in result["predictions"])
    assert P.allowed_service_url("http://127.0.0.1:8001") and P.allowed_service_url("http://localhost:8002/")
    assert not P.allowed_service_url("http://example.com:8001")
    assert not P.allowed_service_url("http://127.0.0.1:8001/admin")
    assert not P.allowed_service_url("file:///etc/passwd")


def test_service_check_reports_unreachable_api_without_raising(tmp_path):
    result = D.check_service("http://127.0.0.1:9", timeout=0.5)
    assert result["health_status"] is None and result["predict_status"] is None
    D.append_service_check(tmp_path, result)
    assert D.read_jsonl(tmp_path / "service_checks.jsonl")[0]["base_url"] == "http://127.0.0.1:9"


def test_server_routes(phase3_run, tmp_path):
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    from dashboard.server import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!DOCTYPE html><div id=root></div>", encoding="utf-8")
    client = TestClient(create_app(phase3_run, web_dist=dist))
    assert client.get("/api/health").json()["web_built"] is True
    assert client.get("/api/state").json()["kpis"]["champion"] >= 1
    assert client.get("/api/scenario/concept_drift").status_code == 200
    assert client.get("/api/scenario/nope").status_code == 404
    assert client.post("/api/service-check", json={"base_url": "http://example.com"}).status_code == 400
    assert client.post("/api/predict", json={"segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB", "date": "2019-07-08",
                                             "time": "17:10"}).json()["predictions"]
    assert client.get("/api/doc/governance").text.startswith("# Phase 3 Governance")
    assert client.get("/drift").text.startswith("<!DOCTYPE html>")
