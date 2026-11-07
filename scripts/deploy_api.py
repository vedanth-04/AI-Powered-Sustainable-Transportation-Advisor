"""Deploy the approved bus API by image digest and preserve a rollback target."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from scripts.smoke_api import smoke_api


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "deploy" / "compose.yml"
DEFAULT_RELEASE_FILE = ROOT / "deploy" / "model-v1.json"
DEFAULT_STATE_DIR = ROOT / "outputs" / "phase2_deploy"
PROJECT_NAME = "phase2-bus-travel-time"
IMAGE_PATTERN = re.compile(
    r"ghcr\.io/vedanth-04/ai-powered-sustainable-transportation-advisor/"
    r"bus-travel-time@sha256:[0-9a-f]{64}"
)
RUN_PATTERN = re.compile(
    r"https://github\.com/vedanth-04/AI-Powered-Sustainable-Transportation-Advisor/"
    r"actions/runs/[1-9][0-9]*",
    re.IGNORECASE,
)
RELEASE_FIELDS = {"image", "model_version", "expected_minutes", "release_run"}


@dataclass(frozen=True)
class Deployment:
    image: str
    model_version: int
    expected_minutes: float
    release_run: str
    port: int


def parse_deployment(record: object, port: int | None = None) -> Deployment:
    fields = RELEASE_FIELDS | {"port"} if port is None else RELEASE_FIELDS
    if not isinstance(record, dict) or record.keys() != fields:
        raise ValueError(f"Expected a deployment record with fields {', '.join(sorted(fields))}.")

    image = record["image"]
    if not isinstance(image, str) or not IMAGE_PATTERN.fullmatch(image):
        raise ValueError("image must be the bus-travel-time GHCR package pinned by SHA-256 digest.")
    version = record["model_version"]
    if type(version) is not int or version < 1:
        raise ValueError("model_version must be a positive integer.")
    minutes = record["expected_minutes"]
    if type(minutes) not in (int, float) or not 0 < minutes <= sys.float_info.max:
        raise ValueError("expected_minutes must be positive and finite.")
    release_run = record["release_run"]
    if not isinstance(release_run, str) or not RUN_PATTERN.fullmatch(release_run):
        raise ValueError("release_run must be a GitHub Actions run URL for this repository.")
    port = record["port"] if port is None else port
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port must be an integer from 1 to 65535.")
    return Deployment(image, version, float(minutes), release_run, port)


def read_state(path: Path) -> tuple[Deployment, Deployment | None]:
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.keys() != {"active", "previous"}:
        raise ValueError("The deployment state must contain active and previous records.")
    active = parse_deployment(state["active"])
    previous = None if state["previous"] is None else parse_deployment(state["previous"])
    return active, previous


def write_state(path: Path, active: Deployment, previous: Deployment | None) -> None:
    state = {"active": asdict(active), "previous": None if previous is None else asdict(previous)}
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".state-", suffix=".tmp", delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(state, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def docker(
    *arguments: str, env: dict[str, str] | None = None, capture: bool = False, timeout: int = 30
) -> str:
    result = subprocess.run(
        ["docker", *arguments],
        env=env,
        stdout=subprocess.PIPE if capture else None,
        text=True,
        check=True,
        timeout=timeout,
    )
    return result.stdout or ""


def compose(release: Deployment, *arguments: str, timeout: int = 30) -> None:
    env = {**os.environ, "BUS_IMAGE_REF": release.image, "BUS_HTTP_PORT": str(release.port)}
    docker(
        "compose", "--project-name", PROJECT_NAME, "--file", str(COMPOSE_FILE),
        *arguments, env=env, timeout=timeout,
    )


def project_exists() -> bool:
    label = f"label=com.docker.compose.project={PROJECT_NAME}"
    return bool(
        docker("ps", "--all", "--quiet", "--filter", label, capture=True).strip()
        or docker("network", "ls", "--quiet", "--filter", label, capture=True).strip()
    )


def activate(release: Deployment) -> None:
    compose(
        release, "up", "--detach", "--no-build", "--pull", "never", "--wait",
        "--wait-timeout", "90", timeout=120,
    )
    smoke_api(f"http://127.0.0.1:{release.port}", release.expected_minutes, release.model_version)


def rollout(state_path: Path, candidate: Deployment) -> None:
    active = previous = None
    if state_path.exists():
        active, previous = read_state(state_path)
    elif project_exists():
        raise ValueError(f"Compose project {PROJECT_NAME} already exists without deployment state.")

    compose(candidate, "config", "--quiet")
    docker("pull", candidate.image, timeout=300)
    if active is not None and active.image != candidate.image:
        try:
            docker("image", "inspect", active.image, capture=True)
        except subprocess.CalledProcessError:
            docker("pull", active.image, timeout=300)

    try:
        activate(candidate)
        write_state(state_path, candidate, previous if active == candidate else active)
    except (Exception, KeyboardInterrupt) as failure:
        try:
            if active is None:
                compose(candidate, "down", "--timeout", "15", timeout=60)
            else:
                activate(active)
        except (Exception, KeyboardInterrupt) as recovery_failure:
            raise RuntimeError(
                f"Deployment failed ({failure}) and recovery failed ({recovery_failure})."
            ) from recovery_failure
        recovered = "The failed project was removed." if active is None else "The previous release was restored."
        raise RuntimeError(f"Deployment failed ({failure}). {recovered}") from failure


def deploy(release_file: Path, state_dir: Path, port: int) -> Deployment:
    candidate = parse_deployment(json.loads(release_file.read_text(encoding="utf-8")), port)
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = state_dir / ".deploy.lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise RuntimeError(f"Deployment lock already exists at {lock}.") from exc
    try:
        rollout(state_dir / "state.json", candidate)
    finally:
        lock.rmdir()
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-file", type=Path, default=DEFAULT_RELEASE_FILE)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    try:
        release = deploy(args.release_file, args.state_dir, args.port)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"{exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Deployment interrupted.\n")
    print(f"Deployed {release.image} at http://127.0.0.1:{release.port}.")


if __name__ == "__main__":
    main()
