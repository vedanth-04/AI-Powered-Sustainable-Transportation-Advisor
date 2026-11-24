"""Compact JSON payloads for the React dashboard, built from the pipeline artifacts.

Pure functions (no web framework), so they are unit-tested directly. Numbers are rounded
to keep payloads small; nothing here changes an artifact.
"""

from __future__ import annotations

from datetime import date, datetime, time
from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path

import numpy as np
import pandas as pd

from dashboard import data as D

SEGMENT_LABEL = {
    "ORR_CHIRAG_TO_NEHRU_PLACE_EB": "ORR eastbound · Route 90",
    "ORR_NEHRU_PLACE_TO_CHIRAG_WB": "ORR westbound · Route 83",
    "MB_SAKET_TO_KHANPUR_EB": "MB Road eastbound · Route 398",
    "MB_KHANPUR_TO_SAKET_WB": "MB Road westbound · Route 399",
}
STAGE_TOOLS = {
    "data": ["Zenodo", "SQLite"], "version": ["DVC"], "labels": ["pandas"], "train": ["scikit-learn", "MLflow"],
    "gate": ["pytest", "quality checks"], "registry": ["MLflow", "Ledger"], "package": ["FastAPI", "Docker", "GitHub Actions"],
    "deploy": ["GHCR", "Compose"], "monitor": ["PSI", "CUSUM"], "retrain": ["Promotion gate"], "rollback": ["Aliases", "Audit log"],
}
DOCS = {"governance": "docs/PHASE3_GOVERNANCE.md", "model_card": "docs/MODEL_CARD.md",
        "presentation": "docs/PHASE3_PRESENTATION.md", "guide": "docs/PHASE3_GUIDE.md"}


def clean(value, digits: int = 4):
    """JSON-safe, rounded copy: NaN/inf become None, numpy scalars become Python values."""
    if isinstance(value, dict):
        return {str(k): clean(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v, digits) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return round(value, digits) if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    return value


def label(segment: str) -> str:
    return SEGMENT_LABEL.get(segment, segment)


# ----- whole-dashboard state -----------------------------------------------------------------------

def dataset_block(dataset: dict) -> dict | None:
    traversals = dataset["traversals"]
    block = {"sources": (dataset["sources"] or {}).get("days", []), "dvc_stages": dataset["dvc_stages"],
             "raw_pointer": dataset["raw_pointer"]}
    if traversals is None:
        return {**block, "available": False}
    counts = traversals.groupby(["date", "segment_id"]).size().reset_index(name="count")
    boxes = []
    for segment, group in traversals.groupby("segment_id"):
        values = group["travel_time_minutes"].to_numpy(dtype=float)
        q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
        iqr = q3 - q1
        inside = values[(values >= q1 - 1.5 * iqr) & (values <= q3 + 1.5 * iqr)]
        boxes.append({"segment": segment, "label": label(segment), "n": len(values), "q1": q1, "median": median, "q3": q3,
                      "low": inside.min(), "high": inside.max(), "mean": values.mean(),
                      "outliers": sorted(values[(values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)].tolist())})
    return {**block, "available": True, "rows": len(traversals), "days": int(traversals["date"].nunique()),
            "segments": int(traversals["segment_id"].nunique()), "routes": int(traversals["route_id"].nunique()),
            "per_day": [{"day": r["date"], "segment": r["segment_id"], "label": label(r["segment_id"]), "count": int(r["count"])}
                        for _, r in counts.iterrows()],
            "boxes": boxes}


def experiments_block(p2: dict) -> dict | None:
    quality = p2["quality"]
    if not quality:
        return None
    rows = [{"model": model, "split": split, "mae": m["mae_minutes"], "rmse": m["rmse_minutes"], "mape": m["mape_percent"],
             "r2": m["r2_score"]}
            for split, key in (("Validation · 5 Jul", "validation_metrics"), ("Test · 8 Jul", "test_metrics"))
            for model, m in quality[key].items()]
    by_segment = p2["test_by_segment"]
    return {"metrics": rows, "checks": [{"name": k, "passed": bool(v)} for k, v in quality["checks"].items()],
            "split_counts": quality["split_counts"], "split_dates": quality["split_dates_ist"],
            "candidate": quality["candidate"], "run_id": quality["candidate_run_id"],
            "test_by_segment": [] if by_segment is None else by_segment.to_dict(orient="records")}


def registry_block(p3: dict) -> dict | None:
    ledger, lifecycle = p3["ledger"], p3["lifecycle"] or {}
    if not ledger:
        return None
    versions = []
    for record in ledger["versions"]:
        versions.append({key: record.get(key) for key in (
            "version", "status", "change_type", "reason", "trigger", "parent_version", "source", "training_window",
            "holdout", "holdout_metrics", "holdout_mae_by_segment", "algorithm", "hyperparameters", "history_policy",
            "feature_schema_sha256", "code", "runtime", "artifact", "gate", "data_validation", "created_at", "mlflow",
            "release")})
    from src.versioning.ledger import diff_versions

    diffs = {f"{a['version']}-{b['version']}": diff_versions(a, b)
             for a in ledger["versions"] for b in ledger["versions"] if a["version"] != b["version"]}
    holdout = p3["holdout"]
    rolling = []
    if holdout is not None:
        frame = D.holdout_rolling(holdout, [f"v{r['version']}" for r in ledger["versions"]])
        for version, group in frame.groupby("version", sort=False):
            rolling.append({"version": version, "points": [[int(r.request), r.rolling_mae, r.time]
                                                           for r in group.itertuples() if pd.notna(r.rolling_mae)]})
    return {"model_name": ledger["model_name"], "aliases": ledger["aliases"], "versions": versions, "diffs": diffs,
            "audit": p3["audit"], "chain": D.verify_chain(p3["audit"]) if p3["audit"] else None,
            "holdout_rolling": rolling, "rollback_drill": lifecycle.get("rollback_drill"),
            "mlflow": (p3.get("release") or {}).get("mlflow") or lifecycle.get("mlflow"), "export": lifecycle.get("export"),
            "trigger": lifecycle.get("retraining_trigger"), "decision": lifecycle.get("decision")}


def monitoring_block(p3: dict) -> dict | None:
    monitoring = p3["monitoring"]
    if not monitoring:
        return None
    scenarios = []
    for name, item in monitoring["scenarios"].items():
        scenarios.append({"name": name, **{k: item.get(k) for k in (
            "title", "description", "onset_ist", "requests", "injected_requests", "alerts_by_type",
            "detection_delay_minutes", "cusum_alarms", "daily", "recommended_actions", "windows_with_alerts")},
            "first_alert": {k: v["detected_at_ist"] for k, v in item["first_alert_after_onset"].items()}})
    return {"model": monitoring["model"], "reference": monitoring["reference"], "kind": monitoring["kind"],
            "generated_at": monitoring["generated_at_utc"], "scenarios": scenarios}


def kpis(registry: dict | None, monitoring: dict | None) -> dict:
    out = {"champion": None, "previous": None, "champion_mae": None, "v1_mae": None, "injected_detected": None,
           "injected_total": None, "real_alarms": None, "chain_valid": None, "audit_entries": 0, "drill_passed": None}
    if registry:
        by_version = {v["version"]: v for v in registry["versions"]}
        champion = by_version.get(registry["aliases"].get("champion"))
        out.update(champion=registry["aliases"].get("champion"), previous=registry["aliases"].get("previous"),
                   champion_mae=(champion or {}).get("holdout_metrics", {}).get("mae_minutes"),
                   v1_mae=by_version.get(1, {}).get("holdout_metrics", {}).get("mae_minutes"),
                   chain_valid=(registry["chain"] or {}).get("valid"), audit_entries=len(registry["audit"]),
                   drill_passed=(registry["rollback_drill"] or {}).get("passed"))
    if monitoring:
        injected = [s for s in monitoring["scenarios"] if s["name"] != "natural"]
        out.update(injected_total=len(injected),
                   injected_detected=sum(any(c.get("ALERT") for c in s["alerts_by_type"].values()) for s in injected),
                   real_alarms=sum(len(s["cusum_alarms"]) for s in monitoring["scenarios"] if s["name"] == "natural"))
    return out


def build_state(root: Path = D.ROOT, phase3_dir: Path = D.PHASE3) -> dict:
    dataset, p2, p3 = D.dataset(root), D.phase2(root), D.phase3(phase3_dir)
    stages = D.pipeline_stages(dataset, p2, p3)
    for stage in stages:
        stage["tools"] = STAGE_TOOLS.get(stage["key"], [])
    registry, monitoring = registry_block(p3), monitoring_block(p3)
    controls = D.governance_controls(p2, p3)
    for control in controls:
        control["passed"] = "PASS" in control.pop("Status")
    return clean({
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "phase3_dir": str(phase3_dir), "segments": SEGMENT_LABEL,
        "artifacts": {"traversals": dataset["traversals"] is not None, "phase2_quality": p2["quality"] is not None,
                      "deployment": p2["deployment"] is not None, "monitoring": monitoring is not None,
                      "ledger": registry is not None, "audit": bool(p3["audit"])},
        "kpis": kpis(registry, monitoring), "pipeline": stages, "dataset": dataset_block(dataset),
        "experiments": experiments_block(p2), "registry": registry, "monitoring": monitoring,
        "deployment": {"release": p2["deployment"], "approval": p2["approval"], "state": p2["deploy_state"],
                       "workflows": p2["workflows"], "serving_manifest": p2["serving_manifest"],
                       "export": (p3["lifecycle"] or {}).get("export"), "checks": p3["service_checks"][-50:]},
        "governance": {"controls": [{"area": c["Area"], "control": c["Control"], "passed": c["passed"],
                                     "evidence": c["Evidence"]} for c in controls],
                       "docs": [name for name, path in DOCS.items() if (root / path).exists()]},
    })


# ----- one scenario in detail ----------------------------------------------------------------------

def build_scenario(phase3_dir: Path, name: str) -> dict | None:
    if name not in D.SCENARIOS:
        return None
    bundle = D.scenario(phase3_dir, name)
    if bundle["summary"] is None:
        return None
    events, windows, cusum = bundle["events"], bundle["windows"], bundle["cusum"]
    rolling = D.rolling_errors(events)
    injected = rolling.loc[rolling["injected"], "label_number"]
    later = rolling.loc[rolling["service_date"] > rolling["service_date"].min(), "label_number"]
    timeline = [[int(r.label_number), r.abs_error, r.rolling_mae, int(r.injected), label(r.segment), r.label_time]
                for r in rolling.itertuples()]
    detectors = []
    for detector in ["all_segments", *sorted(cusum["segment_id"].unique())]:
        part = cusum if detector == "all_segments" else cusum[cusum["segment_id"] == detector]
        value = part["cusum_all"] if detector == "all_segments" else part["cusum_segment"]
        threshold = float((part["threshold_all"] if detector == "all_segments" else part["threshold_segment"]).iloc[0])
        points = [[i + 1, float(v), D.ist(t)] for i, (v, t) in enumerate(zip(value, part["label_at"]))]
        alarm = next((p for p in points if p[1] > threshold), None)
        detectors.append({"name": detector, "label": "All segments" if detector == "all_segments" else label(detector),
                          "threshold": threshold, "points": points, "alarm": alarm})
    features = bundle["features"]
    by_window = {}
    if features is not None and not features.empty:
        for window, group in features.groupby("window", sort=False):
            by_window[window] = group[["feature", "psi", "warn_threshold", "alert_threshold", "null_exceedance",
                                       "ks_pvalue", "status"]].to_dict(orient="records")
    window_rows = []
    for _, w in windows.iterrows():
        window_rows.append({"window": w["window"], "short": f"{int(w['service_date'][-2:])} Jul · {w['period'].replace('_', ' ')}",
                            "requests": int(w["requests"]), "injected": int(w["injected_requests"]),
                            "mae": w["mae_minutes"], "bias": w["bias_minutes"], "normalized_error": w["normalized_error"],
                            "statuses": {"Input drift": w["input_drift_status"], "Prediction drift": w["prediction_drift_status"],
                                         "Data quality": w["data_quality_status"], "Performance": w["performance_status"]},
                            "dq": {c[3:-5]: w[c] for c in windows.columns if c.startswith("dq_") and c.endswith("_rate")}})
    return clean({
        "summary": {**bundle["summary"], "first_alert": {k: v["detected_at_ist"] for k, v in
                                                         bundle["summary"]["first_alert_after_onset"].items()}},
        "windows": window_rows, "timeline": timeline,
        "markers": {"onset": int(injected.min()) if not injected.empty else None,
                    "day_break": int(later.min()) if not later.empty else None},
        "detectors": detectors, "features": by_window,
        "alerts": [{k: a.get(k) for k in ("detected_at_ist", "type", "severity", "scope", "detail")} for a in bundle["alerts"]],
    })


# ----- interactive helpers ------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _model(path: str, mtime: float):
    import joblib

    return joblib.load(BytesIO(Path(path).read_bytes()))


def predict_all(phase3_dir: Path, segment_id: str, day: str, at: str) -> dict:
    """Every registered version's prediction for one request (in-process, from registry artifacts)."""
    from sklearn import __version__ as installed
    from src.features.segment_config import get_segment
    from src.features.label_generation import IST_OFFSET
    from src.monitoring.replay import FEATURES, serving_features

    ledger = D.read_json(phase3_dir / "registry" / "model_versions.json")
    if not ledger:
        return {"error": "No version ledger yet. Run python -m scripts.run_phase3 first.", "predictions": []}
    segment = get_segment(segment_id)
    entry = datetime.combine(date.fromisoformat(day), time.fromisoformat(at)).replace(tzinfo=IST_OFFSET).timestamp()
    request = pd.DataFrame([{"segment_id": segment_id, "direction": segment.direction, "segment_length_km": segment.length_km,
                             "route_id": segment.primary_routes[0], "entry_ts_sent": entry}])
    features = serving_features(request)[FEATURES]
    out = []
    for record in ledger["versions"]:
        path = phase3_dir / (record.get("artifact") or {}).get("path", "missing")
        aliases = [alias for alias, version in ledger["aliases"].items() if version == record["version"]]
        row = {"version": record["version"], "status": record["status"], "aliases": aliases, "minutes": None, "note": None}
        if record["runtime"]["scikit-learn"] != installed:
            row["note"] = f"saved with scikit-learn {record['runtime']['scikit-learn']}, this server has {installed}"
        elif not path.exists():
            row["note"] = "artifact missing"
        else:
            row["minutes"] = float(_model(str(path), path.stat().st_mtime).predict(features)[0])
        out.append(row)
    return clean({"segment": segment_id, "label": label(segment_id), "route": segment.primary_routes[0],
                  "in_api_scope": segment_id == "ORR_CHIRAG_TO_NEHRU_PLACE_EB", "entry_ist": f"{day} {at}",
                  "predictions": out})


def allowed_service_url(url: str) -> bool:
    """The health probe only talks to services on this machine."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and parts.hostname in ("127.0.0.1", "localhost") and not parts.path.strip("/")
