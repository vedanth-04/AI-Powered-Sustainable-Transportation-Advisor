"""Ensure demo evidence fails when deployment identity or API behavior differs."""

from dataclasses import asdict
from http.client import IncompleteRead
import json

import pytest

from scripts import deploy_api, verify_deployment


@pytest.fixture
def deployed(tmp_path, monkeypatch):
    release = json.loads(deploy_api.DEFAULT_RELEASE_FILE.read_text(encoding="utf-8"))
    active = deploy_api.parse_deployment(release, 8001)
    release_file = tmp_path / "release.json"
    release_file.write_text(json.dumps(release), encoding="utf-8")
    state_file = tmp_path / "state.json"
    deploy_api.write_state(state_file, active, None)
    container = {
        "id": "container-id", "image_ref": active.image, "image_id": "sha256:image-id",
        "running": True, "health": "healthy",
        "ports": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8001"}]},
        "source_revision": "a" * 40,
    }
    digests = [active.image]

    def docker(*args, **kwargs):
        if args[0] == "ps":
            return "container-id\n"
        if args[0] == "inspect":
            return json.dumps(container)
        if args[:2] == ("image", "inspect"):
            return json.dumps(digests)
        pytest.fail(f"Unexpected Docker operation: {args}")

    metadata = {"model_version": 1, "history_policy": "cold_start_v1"}
    prediction = {**metadata, "estimate_source": "model", "duration_minutes": active.expected_minutes}

    def request_json(url, *, payload=None, expected_status=200):
        assert url.startswith("http://127.0.0.1:8001/")
        if expected_status == 422:
            return {"detail": "Invalid demo request"}
        if url.endswith("/health"):
            return {**metadata, "status": "ready", "model_name": "BusTravelTimePredictor"}
        return prediction

    monkeypatch.setattr(verify_deployment, "docker", docker)
    monkeypatch.setattr(verify_deployment, "request_json", request_json)
    return state_file, release_file, active, container, digests, prediction


def test_runtime_evidence_records_observations(deployed):
    state_file, release_file, active, _, _, _ = deployed
    report = verify_deployment.collect_evidence(state_file, release_file)
    assert report["overall_passed"] is True
    assert report["expected_deployment"] == asdict(active)
    assert len(report["passed_checks"]) == 8
    assert [item["status"] for item in report["http_checks"]] == [200, 200, 422, 422, 422]
    assert report["http_checks"][1]["response"]["duration_minutes"] == active.expected_minutes


@pytest.mark.parametrize("mismatch", ["image-reference", "image-content", "public-port", "readiness", "prediction"])
def test_wrong_runtime_is_never_reported_as_passing(deployed, mismatch):
    state_file, release_file, _, container, digests, prediction = deployed
    if mismatch == "image-reference":
        container["image_ref"] = "bus-travel-time:v1"
    elif mismatch == "image-content":
        digests.clear()
    elif mismatch == "public-port":
        container["ports"]["8000/tcp"][0]["HostIp"] = "0.0.0.0"
    elif mismatch == "readiness":
        container["health"] = "unhealthy"
    else:
        prediction["duration_minutes"] = 999
    report = verify_deployment.collect_evidence(state_file, release_file)
    assert report["overall_passed"] is False
    assert report["failed_check"]
    assert report["error"]


def test_failed_cli_replaces_old_success_report_and_preserves_state(deployed, tmp_path, monkeypatch):
    state_file, release_file, _, _, digests, _ = deployed
    original = state_file.read_bytes()
    output = tmp_path / "evidence.json"
    output.write_text('{"overall_passed":true}', encoding="utf-8")
    digests.clear()
    monkeypatch.setattr("sys.argv", [
        "verify_deployment", "--state-file", str(state_file),
        "--release-file", str(release_file), "--output", str(output),
    ])
    with pytest.raises(SystemExit) as exc:
        verify_deployment.main()
    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8"))["overall_passed"] is False
    assert state_file.read_bytes() == original


def test_interrupted_http_response_is_recorded_as_failure(deployed, monkeypatch):
    state_file, release_file, _, _, _, _ = deployed

    def truncated_response(*args, **kwargs):
        raise IncompleteRead(b'{"status":', 10)

    monkeypatch.setattr(verify_deployment, "request_json", truncated_response)
    report = verify_deployment.collect_evidence(state_file, release_file)
    assert report["overall_passed"] is False
    assert report["failed_check"] == "API readiness and model version"
