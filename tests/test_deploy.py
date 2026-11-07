"""Check deployment state and recovery without running Docker."""

from dataclasses import asdict, replace
import json
import subprocess

import pytest

from scripts import deploy_api


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    release_file = tmp_path / "release.json"
    release = json.loads(deploy_api.DEFAULT_RELEASE_FILE.read_text(encoding="utf-8"))
    release_file.write_text(json.dumps(release), encoding="utf-8")
    candidate = deploy_api.parse_deployment(release, 8001)
    calls = []

    def docker(*arguments, **options):
        calls.append((arguments, options))
        return ""

    monkeypatch.setattr(deploy_api, "docker", docker)
    monkeypatch.setattr(deploy_api, "smoke_api", lambda *args: None)
    return release_file, tmp_path / "state", candidate, calls


def test_success_records_previous_and_repeated_deploy_keeps_it(deployment):
    release_file, state_dir, candidate, calls = deployment
    deploy_api.deploy(release_file, state_dir, 8001)
    deploy_api.deploy(release_file, state_dir, 8002)
    deploy_api.deploy(release_file, state_dir, 8002)

    active, previous = deploy_api.read_state(state_dir / "state.json")
    assert active == replace(candidate, port=8002)
    assert previous == candidate
    assert not (state_dir / ".deploy.lock").exists()
    assert calls[0][0][:2] == ("ps", "--all")
    up_calls = [(args, options) for args, options in calls if "up" in args]
    assert len(up_calls) == 3
    assert up_calls[-1][1]["env"]["BUS_HTTP_PORT"] == "8002"
    assert up_calls[-1][1]["env"]["BUS_IMAGE_REF"] == candidate.image


@pytest.mark.parametrize("failure_stage", ["activation", "smoke", "state-write"])
def test_failed_candidate_restores_active_without_changing_state(
    deployment, monkeypatch, failure_stage
):
    release_file, state_dir, candidate, calls = deployment
    state_dir.mkdir()
    deploy_api.write_state(state_dir / "state.json", candidate, None)
    original_state = (state_dir / "state.json").read_bytes()
    smoke_ports = []
    docker = deploy_api.docker

    def fail_activation(*arguments, **options):
        if "up" in arguments and options["env"]["BUS_HTTP_PORT"] == "8002":
            raise subprocess.CalledProcessError(1, ["docker", *arguments])
        return docker(*arguments, **options)

    def smoke(url, *args):
        smoke_ports.append(url)
        if url.endswith(":8002") and failure_stage == "smoke":
            raise ValueError("Wrong prediction")

    def fail_write(*args):
        raise OSError("State is not writable")

    monkeypatch.setattr(deploy_api, "smoke_api", smoke)
    if failure_stage == "activation":
        monkeypatch.setattr(deploy_api, "docker", fail_activation)
    if failure_stage == "state-write":
        monkeypatch.setattr(deploy_api, "write_state", fail_write)

    with pytest.raises(RuntimeError, match="previous release was restored"):
        deploy_api.deploy(release_file, state_dir, 8002)

    assert smoke_ports[-1] == "http://127.0.0.1:8001"
    assert (state_dir / "state.json").read_bytes() == original_state
    assert not (state_dir / ".deploy.lock").exists()
    assert not any("down" in args for args, _ in calls)


def test_first_failed_deploy_removes_only_its_new_project(deployment, monkeypatch):
    release_file, state_dir, _, calls = deployment

    def fail_smoke(*args):
        raise ValueError("Wrong prediction")

    monkeypatch.setattr(deploy_api, "smoke_api", fail_smoke)
    with pytest.raises(RuntimeError, match="failed project was removed"):
        deploy_api.deploy(release_file, state_dir, 8001)

    down = [args for args, _ in calls if "down" in args]
    assert len(down) == 1
    assert down[0][1:3] == ("--project-name", deploy_api.PROJECT_NAME)
    assert "--volumes" not in down[0]
    assert not (state_dir / "state.json").exists()


def test_existing_project_without_state_is_left_alone(deployment, monkeypatch):
    release_file, state_dir, _, calls = deployment

    def existing_container(*args, **options):
        calls.append((args, options))
        return "existing-container\n"

    monkeypatch.setattr(deploy_api, "docker", existing_container)
    with pytest.raises(ValueError, match="already exists without deployment state"):
        deploy_api.deploy(release_file, state_dir, 8001)
    assert len(calls) == 1
    assert not (state_dir / ".deploy.lock").exists()


def test_pull_failure_does_not_activate_or_remove_project(deployment, monkeypatch):
    release_file, state_dir, _, calls = deployment
    docker = deploy_api.docker

    def fail_pull(*args, **options):
        if args[0] == "pull":
            raise subprocess.CalledProcessError(1, ["docker", *args])
        return docker(*args, **options)

    monkeypatch.setattr(deploy_api, "docker", fail_pull)
    with pytest.raises(subprocess.CalledProcessError):
        deploy_api.deploy(release_file, state_dir, 8001)
    assert not any("up" in args or "down" in args for args, _ in calls)
    assert not (state_dir / ".deploy.lock").exists()


@pytest.mark.parametrize(
    "field, value",
    [("image", "ghcr.io/unrelated/image@sha256:" + "a" * 64),
     ("model_version", True), ("expected_minutes", float("nan")), ("port", 0)],
)
def test_invalid_release_metadata_is_rejected(deployment, field, value):
    _, _, candidate, _ = deployment
    record = {**asdict(candidate), field: value}
    with pytest.raises(ValueError):
        deploy_api.parse_deployment(record)
