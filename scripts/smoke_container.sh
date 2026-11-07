#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  printf 'Usage: %s IMAGE MODEL_VERSION EXPECTED_MINUTES\n' "$0" >&2
  exit 2
fi

image=$1
model_version=$2
expected_minutes=$3
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

# Create first so the container can be removed even if it fails to start.
container=$(docker create --publish 127.0.0.1::8000 -- "$image")
cleanup() {
  local status=$?
  if [[ $status -ne 0 ]]; then
    docker logs "$container" >&2 || true
  fi
  if ! docker rm --force "$container" >/dev/null; then
    printf 'Could not remove smoke-test container %s.\n' "$container" >&2
    if [[ $status -eq 0 ]]; then status=1; fi
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker start "$container" >/dev/null

for ((attempt = 1; attempt <= 30; attempt++)); do
  state=$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")
  case "$state" in
    'running healthy') break ;;
    'running starting') sleep 2 ;;
    *)
      printf 'Smoke-test container cannot become healthy in state %s.\n' "$state" >&2
      exit 1
      ;;
  esac
done
if [[ $state != 'running healthy' ]]; then
  printf 'Smoke-test container did not become healthy before the timeout.\n' >&2
  exit 1
fi

address=$(docker port "$container" 8000/tcp)
if [[ ! $address =~ ^127\.0\.0\.1:[0-9]+$ ]]; then
  printf 'Expected a localhost port for the smoke-test container, got %s.\n' "$address" >&2
  exit 1
fi

python3 -m scripts.smoke_api --base-url "http://$address" \
  --model-version "$model_version" --expected-minutes "$expected_minutes"
