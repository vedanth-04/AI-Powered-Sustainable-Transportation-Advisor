"""Save read-only checks of the released image and the running local API."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from http.client import HTTPException
import json
import math
from pathlib import Path
import subprocess

from scripts.deploy_api import (
    DEFAULT_RELEASE_FILE, DEFAULT_STATE_DIR, PROJECT_NAME, ROOT,
    docker, parse_deployment, read_state,
)
from scripts.smoke_api import expect_fields, request_json


DEFAULT_OUTPUT = ROOT / "outputs" / "phase2_demo" / "deployment_check.json"
CONTAINER_FORMAT = (
    '{"id":{{json .Id}},"image_ref":{{json .Config.Image}},'
    '"image_id":{{json .Image}},"running":{{json .State.Running}},'
    '"health":{{json .State.Health.Status}},'
    '"ports":{{json .NetworkSettings.Ports}},'
    '"source_revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}}}'
)


def collect_evidence(state_file: Path, release_file: Path) -> dict:
    """Collect actual observations; retain partial results when a check fails."""
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "local_runtime_verification",
        "overall_passed": False,
        "passed_checks": [],
        "http_checks": [],
    }
    stage = "deployment state matches the approved release"
    try:
        active, _ = read_state(state_file)
        approved = parse_deployment(json.loads(release_file.read_text(encoding="utf-8")), active.port)
        report["expected_deployment"] = asdict(approved)
        if active != approved:
            raise ValueError("Active deployment state differs from the approved release file.")
        report["passed_checks"].append(stage)

        stage = "exactly one Compose API container"
        containers = docker(
            "ps", "--all", "--quiet",
            "--filter", f"label=com.docker.compose.project={PROJECT_NAME}",
            "--filter", "label=com.docker.compose.service=api", capture=True,
        ).split()
        if len(containers) != 1:
            raise ValueError(f"Expected one {PROJECT_NAME} API container, found {len(containers)}.")
        report["passed_checks"].append(stage)

        stage = "container image digest and readiness"
        container = json.loads(docker("inspect", "--format", CONTAINER_FORMAT, containers[0], capture=True))
        report["container"] = container
        if container["image_ref"] != approved.image:
            raise ValueError("The container was not started using the approved image digest.")
        digests = json.loads(docker(
            "image", "inspect", "--format", "{{json .RepoDigests}}", container["image_id"], capture=True,
        ))
        report["image_repo_digests"] = digests
        if approved.image not in (digests or []):
            raise ValueError("The container's image does not carry the approved repository digest.")
        if container["running"] is not True or container["health"] != "healthy":
            raise ValueError("The Compose API container is not running and healthy.")
        if container["ports"] != {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(active.port)}]}:
            raise ValueError("The container port binding differs from the expected localhost port.")
        report["passed_checks"].append(stage)

        base_url = f"http://127.0.0.1:{active.port}"
        metadata = {"model_version": approved.model_version, "history_policy": "cold_start_v1"}
        stage = "API readiness and model version"
        health = request_json(f"{base_url}/health")
        report["http_checks"].append({"case": "readiness", "status": 200, "response": health})
        expect_fields(health, {**metadata, "status": "ready", "model_name": "BusTravelTimePredictor"})
        report["passed_checks"].append(stage)

        payload = {
            "segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB",
            "route_id": "90",
            "entry_at": "2019-07-08T17:10:00+05:30",
        }
        endpoint = f"{base_url}/predict/bus"
        stage = "approved Route 90 prediction"
        prediction = request_json(endpoint, payload=payload)
        report["http_checks"].append({
            "case": "approved_prediction", "status": 200, "request": payload, "response": prediction,
        })
        expect_fields(prediction, {**metadata, "estimate_source": "model"})
        minutes = prediction.get("duration_minutes")
        if type(minutes) not in (int, float) or not math.isclose(
            minutes, approved.expected_minutes, rel_tol=0, abs_tol=1e-8,
        ):
            raise ValueError(f"Expected duration {approved.expected_minutes}, got {minutes!r}.")
        report["passed_checks"].append(stage)

        invalid_requests = {
            "unsupported_route": {**payload, "route_id": "999"},
            "unsupported_segment": {**payload, "segment_id": "unknown"},
            "missing_timezone": {**payload, "entry_at": "2019-07-08T17:10:00"},
        }
        for case, invalid in invalid_requests.items():
            stage = f"HTTP 422 for {case}"
            response = request_json(endpoint, payload=invalid, expected_status=422)
            report["http_checks"].append({
                "case": case, "status": 422, "request": invalid, "response": response,
            })
            report["passed_checks"].append(stage)
        report["overall_passed"] = True
    except (OSError, ValueError, KeyError, TypeError, HTTPException, subprocess.SubprocessError) as exc:
        report["failed_check"] = stage
        report["error"] = str(exc)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_DIR / "state.json")
    parser.add_argument("--release-file", type=Path, default=DEFAULT_RELEASE_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    # An evidence output must never replace the inputs needed to manage deployment.
    if args.output.resolve() in {args.state_file.resolve(), args.release_file.resolve()}:
        parser.error("The evidence output must differ from the state and release files.")
    report = collect_evidence(args.state_file, args.release_file)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        parser.exit(1, f"Could not save deployment evidence: {exc}\n")
    if not report["overall_passed"]:
        parser.exit(1, f"Verification failed at {report['failed_check']}: {report['error']}\nReport: {args.output}\n")
    print(f"Passed {len(report['passed_checks'])} deployment checks. Report: {args.output}")


if __name__ == "__main__":
    main()
