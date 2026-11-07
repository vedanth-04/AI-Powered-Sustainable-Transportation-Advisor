"""Check the running API against the expected Route 90 prediction."""

import argparse
import json
import math
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(url, *, payload=None, expected_status=200):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as exc:
        response = exc

    with response:
        if response.status != expected_status:
            raise ValueError(
                f"{request.get_method()} {url}: expected HTTP {expected_status}, got {response.status}"
            )
        body = json.load(response)
    if not isinstance(body, dict):
        raise ValueError(f"{request.get_method()} {url}: expected a JSON object")
    return body


def expect_fields(body, expected):
    for field, value in expected.items():
        actual = body.get(field)
        if type(actual) is not type(value) or actual != value:
            raise ValueError(f"Expected {field}={value!r}, got {actual!r}")


def smoke_api(base_url: str, expected_minutes: float, model_version: int) -> None:
    base_url = base_url.rstrip("/")
    metadata = {"model_version": model_version, "history_policy": "cold_start_v1"}
    health = request_json(f"{base_url}/health")
    expect_fields(health, {**metadata, "status": "ready", "model_name": "BusTravelTimePredictor"})

    request = {
        "segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB",
        "route_id": "90",
        "entry_at": "2019-07-08T17:10:00+05:30",
    }
    endpoint = f"{base_url}/predict/bus"
    prediction = request_json(endpoint, payload=request)
    expect_fields(prediction, {**metadata, "estimate_source": "model"})
    minutes = prediction.get("duration_minutes")
    if type(minutes) not in (int, float) or not math.isclose(
        minutes, expected_minutes, rel_tol=0, abs_tol=1e-8
    ):
        raise ValueError(f"Expected duration_minutes={expected_minutes}, got {minutes!r}")

    request_json(endpoint, payload={**request, "route_id": "999"}, expected_status=422)
    print(
        f"API smoke passed for model v{model_version}. Route 90 predicted {minutes} minutes. "
        "The unsupported route returned HTTP 422."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--expected-minutes", type=float, required=True)
    parser.add_argument("--model-version", type=int, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.expected_minutes) or args.expected_minutes <= 0 or args.model_version <= 0:
        parser.error("Expected minutes and model version must be positive and finite.")
    try:
        smoke_api(args.base_url, args.expected_minutes, args.model_version)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"API smoke failed: {exc}\n")


if __name__ == "__main__":
    main()
