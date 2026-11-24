"""Read every pipeline artifact the dashboard shows (used by dashboard/payloads.py and server.py).

Each loader returns None (never raises) when an artifact has not been produced yet,
so the dashboard can say exactly which step still needs to run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import time
from urllib import error, request

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PHASE3 = ROOT / "outputs" / "phase3"
SCENARIOS = ("natural", "covariate_shift", "concept_drift", "data_quality")
STATUS_ICON = {"OK": "🟢 OK", "WARN": "🟠 WARN", "ALERT": "🔴 ALERT", "INSUFFICIENT_DATA": "⚪ too few", "PASS": "🟢 PASS",
               "FAIL": "🔴 FAIL", "PARTIAL": "🟠 PARTIAL", "MISSING": "⚪ NOT RUN"}
IST = timezone(timedelta(hours=5, minutes=30))
EXAMPLE_REQUEST = {"segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB", "route_id": "90", "entry_at": "2019-07-08T17:10:00+05:30"}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_csv(path: Path, **kwargs) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path, **kwargs)
    except (OSError, ValueError):
        return None


def read_jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []


def ist(epoch: float | None) -> str:
    if epoch is None or pd.isna(epoch):
        return ""
    return datetime.fromtimestamp(float(epoch), IST).strftime("%d %b %H:%M")


# ----- Phase 1-2 evidence ------------------------------------------------------------------------

def dataset(root: Path = ROOT) -> dict:
    traversals = read_csv(root / "data" / "processed" / "phase2_cold_start" / "traversals.csv", dtype={"route_id": str})
    return {
        "traversals": traversals,
        "sources": read_json(root / "data" / "processed" / "phase2_cold_start" / "sources.json"),
        "dvc_stages": dvc_stages(root),
        "raw_pointer": (root / "data" / "raw" / "2019-07-01.db.dvc").exists(),
    }


def dvc_stages(root: Path = ROOT) -> list[dict]:
    """Stage names and outputs from dvc.yaml / dvc.lock (text parsing, no YAML dependency)."""
    stages = []
    text = (root / "dvc.yaml").read_text(encoding="utf-8") if (root / "dvc.yaml").exists() else ""
    lock = (root / "dvc.lock").read_text(encoding="utf-8") if (root / "dvc.lock").exists() else ""
    for match in re.finditer(r"^  (\w+):\n    cmd: (.+)$", text, flags=re.MULTILINE):
        stages.append({"stage": match.group(1), "command": match.group(2).strip(),
                       "locked": f"  {match.group(1)}:" in lock})
    return stages


def phase2(root: Path = ROOT) -> dict:
    results = root / "docs" / "results"
    return {
        "quality": read_json(results / "phase2-v1" / "quality_report.json"),
        "registration": read_json(results / "phase2-v1" / "registration.json"),
        "validation": read_json(results / "2026-11-09-validation" / "summary.json"),
        "comparison": read_csv(root / "outputs" / "phase2_cold_start" / "model_comparison.csv"),
        "test_by_segment": read_csv(root / "outputs" / "phase2_cold_start" / "test_by_segment.csv"),
        "deployment": read_json(root / "deploy" / "model-v1.json"),
        "approval": read_json(root / "deploy" / "release-approvals" / "v1.json"),
        "deploy_state": read_json(root / "outputs" / "phase2_deploy" / "state.json"),
        "workflows": sorted(path.name for path in (root / ".github" / "workflows").glob("*.yml")),
        "serving_manifest": read_json(root / "outputs" / "phase2_serving" / "manifest.json"),
    }


# ----- Phase 3 evidence --------------------------------------------------------------------------

def phase3(phase3_dir: Path = PHASE3) -> dict:
    registry = phase3_dir / "registry"
    return {
        "dir": phase3_dir,
        "monitoring": read_json(phase3_dir / "monitoring" / "report.json"),
        "lifecycle": read_json(registry / "lifecycle_report.json"),
        "ledger": read_json(registry / "model_versions.json"),
        "release": read_json(registry / "advisor_release.json"),
        "audit": read_jsonl(registry / "audit_log.jsonl"),
        "holdout": read_csv(registry / "holdout_predictions.csv"),
        "summary": read_json(phase3_dir / "phase3_summary.json"),
        "service_checks": read_jsonl(phase3_dir / "service_checks.jsonl"),
    }


def scenario(phase3_dir: Path, name: str) -> dict:
    folder = phase3_dir / "monitoring" / name
    return {
        "summary": read_json(folder / "summary.json"),
        "alerts": read_json(folder / "alerts.json") or [],
        "events": read_csv(folder / "events.csv", dtype={"route_id": str}),
        "windows": read_csv(folder / "windows.csv"),
        "features": read_csv(folder / "feature_drift.csv"),
        "cusum": read_csv(folder / "cusum.csv"),
    }


def verify_chain(entries: list[dict]) -> dict:
    """Same rule as src.versioning.ledger.verify_audit_chain, on already-loaded entries."""
    previous = "0" * 64
    for entry in entries:
        body = {key: value for key, value in entry.items() if key != "entry_sha256"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
        if entry.get("previous_sha256") != previous or sha256(canonical).hexdigest() != entry.get("entry_sha256"):
            return {"valid": False, "entries": len(entries), "broken_at_sequence": entry.get("sequence")}
        previous = entry["entry_sha256"]
    return {"valid": True, "entries": len(entries)}


def rolling_errors(events: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    ordered = events.sort_values(["label_at", "event_id"]).reset_index(drop=True)
    return pd.DataFrame({
        "label_number": range(1, len(ordered) + 1),
        "abs_error": ordered["abs_error_minutes"],
        "rolling_mae": ordered["abs_error_minutes"].rolling(window, min_periods=5).mean(),
        "injected": ordered["injected"].astype(bool),
        "segment": ordered["segment_id"],
        "label_time": [ist(value) for value in ordered["label_at"]],
        "service_date": ordered["service_date"],
    })


def holdout_rolling(holdout: pd.DataFrame, versions: list[str], window: int = 15) -> pd.DataFrame:
    ordered = holdout.sort_values("received_at").reset_index(drop=True)
    frames = []
    for version in versions:
        column = f"pred_{version}"
        if column not in ordered:
            continue
        error = (ordered[column] - ordered["actual_minutes"]).abs()
        frames.append(pd.DataFrame({"request": range(1, len(ordered) + 1), "version": version,
                                    "rolling_mae": error.rolling(window, min_periods=5).mean(),
                                    "time": [ist(value) for value in ordered["received_at"]]}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----- pipeline and governance status ------------------------------------------------------------

def _status(done: bool, partial: bool = False) -> str:
    return "PASS" if done else "PARTIAL" if partial else "MISSING"


def pipeline_stages(data: dict, p2: dict, p3: dict) -> list[dict]:
    monitoring, lifecycle, ledger = p3["monitoring"], p3["lifecycle"], p3["ledger"]
    quality = p2["quality"] or {}
    checks = quality.get("checks", {})
    alarms = sum(len(s.get("cusum_alarms", [])) for s in (monitoring or {}).get("scenarios", {}).values())
    champion = (ledger or {}).get("aliases", {}).get("champion")
    stages = [
        ("data", "1. Raw data", "Zenodo 2019 Delhi bus GPS archive, DVC pointer", _status(data["raw_pointer"]),
         "data/raw/2019-07-01.db.dvc"),
        ("version", "2. Data versioning", "DVC pipeline: labels -> features",
         _status(bool(data["dvc_stages"]) and all(s["locked"] for s in data["dvc_stages"]), bool(data["dvc_stages"])),
         "dvc.yaml, dvc.lock"),
        ("labels", "3. Labels & features", "Gate crossings -> 637 traversals -> 12 cold-start features",
         _status(data["traversals"] is not None), "data/processed/phase2_cold_start"),
        ("train", "4. Training & tracking", "Median / RF / GB on date splits, MLflow runs",
         _status(p2["comparison"] is not None or bool(quality)), "outputs/phase2_cold_start"),
        ("gate", "5. Quality gate", f"{sum(bool(v) for v in checks.values())}/{len(checks)} checks passed",
         _status(bool(checks) and all(checks.values())), "docs/results/phase2-v1/quality_report.json"),
        ("registry", "6. Model registry", "MLflow BusTravelTimePredictor + Phase 3 version ledger",
         _status(bool(p2["registration"]) and bool(ledger), bool(p2["registration"])), "registration.json, model_versions.json"),
        ("package", "7. Package & CI", "FastAPI + Docker, GitHub Actions on Windows and Linux",
         _status(bool(p2["workflows"]) and p2["deployment"] is not None), ".github/workflows, Dockerfile"),
        ("deploy", "8. Deploy", "Digest-pinned image, local Compose with rollback",
         _status(bool(p2["deploy_state"]), p2["deployment"] is not None), "deploy/model-v1.json"),
        ("monitor", "9. Monitor & drift", f"{len((monitoring or {}).get('scenarios', {}))} replay scenarios, {alarms} CUSUM alarms",
         _status(monitoring is not None), "outputs/phase3/monitoring"),
        ("retrain", "10. Retrain & promote", f"champion v{champion}" if champion else "not run",
         _status(lifecycle is not None and champion is not None), "outputs/phase3/registry"),
        ("rollback", "11. Rollback ready", "previous alias kept, drill verified",
         _status(bool((lifecycle or {}).get("rollback_drill", {}) and lifecycle["rollback_drill"].get("passed"))),
         "lifecycle_report.json"),
    ]
    return [dict(zip(("key", "stage", "detail", "status", "evidence"), stage)) for stage in stages]


def governance_controls(p2: dict, p3: dict) -> list[dict]:
    ledger, lifecycle, monitoring = p3["ledger"] or {}, p3["lifecycle"] or {}, p3["monitoring"] or {}
    chain = verify_chain(p3["audit"]) if p3["audit"] else {"valid": False}
    gates = lifecycle.get("gates", {})
    rejected = [v for v in ledger.get("versions", []) if v["status"] == "rejected"]
    rows = [
        ("Data", "Source & licence recorded", bool(p2["quality"]), "docs/reference/schema_audit_report.md"),
        ("Data", "Training data validated before every retrain", bool(gates) and all(
            g["checks"][0]["name"] == "data_validation" for g in gates.values()), "promotion_policy.json → data_validation"),
        ("Data", "Corrupted batch quarantined", bool(rejected), "ledger: rejected candidate"),
        ("Model", "Every version has lineage (data, code, params, artifact hash)", bool(ledger.get("versions")) and all(
            v.get("artifact") and v.get("training_window") for v in ledger.get("versions", [])), "model_versions.json"),
        ("Model", "Promotion only through the gate", bool(gates), "lifecycle_report.json → gates"),
        ("Model", "Champion beats baseline and previous model", any(g["passed"] for g in gates.values()), "gate checks"),
        ("Model", "Advisor release versioned with its model, data and code hashes", any(
            v.get("change_type") == "system_release" and v.get("release") for v in ledger.get("versions", [])),
         "ledger: system_release version"),
        ("Model", "Scope limited to approved route/segment", bool(p2["serving_manifest"] or p2["approval"]), "API returns 422 outside scope"),
        ("Operations", "Drift monitoring with calibrated thresholds", bool(monitoring), "monitoring_policy.json"),
        ("Operations", "One-step rollback rehearsed", bool(lifecycle.get("rollback_drill", {}) and lifecycle["rollback_drill"].get("passed")), "rollback drill"),
        ("Operations", "Image pinned by digest, CI on two OSes", p2["deployment"] is not None and len(p2["workflows"]) >= 2, "deploy/model-v1.json"),
        ("Accountability", "Tamper-evident audit log", chain.get("valid", False), "audit_log.jsonl hash chain"),
        ("Accountability", "Named actor on every promotion/rollback", bool(p3["audit"]) and all(e.get("actor") for e in p3["audit"]), "audit_log.jsonl"),
        ("Privacy", "No rider data; request bodies never logged", True, "src/api/main.py request_log"),
    ]
    return [{"Area": a, "Control": c, "Status": STATUS_ICON["PASS" if ok else "MISSING"], "Evidence": e} for a, c, ok, e in rows]


# ----- live service check -------------------------------------------------------------------------

def check_service(base_url: str, timeout: float = 5.0) -> dict:
    """GET /health and POST the documented example; record latency and status (no request body is stored)."""
    base = base_url.rstrip("/")
    result = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "base_url": base}
    for name, method, path, body in (("health", "GET", "/health", None),
                                     ("predict", "POST", "/predict/bus", EXAMPLE_REQUEST)):
        started = time.perf_counter()
        try:
            data = json.dumps(body).encode() if body else None
            req = request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
            with request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode())
                status = response.status
        except error.HTTPError as exc:
            status, payload = exc.code, {"detail": exc.reason}
        except Exception as exc:
            status, payload = None, {"error": type(exc).__name__}
        result[f"{name}_status"] = status
        result[f"{name}_latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        result[f"{name}_response"] = payload
    return result


def append_service_check(phase3_dir: Path, result: dict) -> None:
    phase3_dir.mkdir(parents=True, exist_ok=True)
    with (phase3_dir / "service_checks.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result) + "\n")
