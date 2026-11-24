"""Historical replay: serve held-out traffic in time order, reveal labels later, detect drift.

This is a historical replay of 2019 data, not live monitoring of a public service.
Predictions use the same cold-start features as the API; labels arrive when the bus
exits the segment, exactly as delayed ground truth would arrive in production.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import zlib

import numpy as np
import pandas as pd

from src.config import OUTPUTS_DIR, PROJECT_ROOT, RANDOM_SEED
from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, engineer_features
from src.features.label_generation import IST_OFFSET
from src.monitoring.drift import calibrate_cusum_threshold, calibrated_mean_shift, calibrated_psi, Cusum
from src.monitoring.quality import QualityReference, request_flags, summarize_quality
from src.monitoring.scenarios import apply_scenario, base_events

FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
DEFAULT_POLICY = PROJECT_ROOT / "config" / "phase3" / "monitoring_policy.json"
DEFAULT_TRAVERSALS = PROJECT_ROOT / "data" / "processed" / "phase2_cold_start" / "traversals.csv"
DEFAULT_BUNDLE = OUTPUTS_DIR / "phase2_serving"
SEVERITY_RANK = {"OK": 0, "WARN": 1, "ALERT": 2}


@dataclass(frozen=True)
class ModelHandle:
    name: str
    version: int
    model: object
    source: str  # approved_bundle | reproduced_from_training_split | registry
    sha256: str | None


def ist_text(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), IST_OFFSET).strftime("%Y-%m-%d %H:%M")


def load_policy(path: Path = DEFAULT_POLICY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_splits(traversals_path: Path, policy: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from src.models.train import load_training_features
    from src.models.train_cold_start import split_by_date

    replay = policy["replay"]
    return split_by_date(load_training_features(traversals_path),
                         date.fromisoformat(replay["validation_start_ist"]),
                         date.fromisoformat(replay["test_start_ist"]))


def load_approved_v1(bundle_dir: Path) -> ModelHandle:
    """Load the exact approved v1 artifact with all Phase 2 integrity checks."""
    from src.api.bundle import load_bundle

    bundle = load_bundle(bundle_dir)
    return ModelHandle(bundle.manifest.model_name, bundle.manifest.model_version, bundle.model,
                       "approved_bundle", bundle.manifest.model_sha256)


def reproduce_v1(training: pd.DataFrame) -> ModelHandle:
    """Refit v1's configuration on v1's training split (for machines without the approved bundle)."""
    from src.models.train import build_candidate_models

    model = build_candidate_models()["Gradient Boosting Regressor"]
    features = serving_features(base_events(training))
    model.fit(features[FEATURES], base_events(training)["actual_minutes"])
    return ModelHandle("BusTravelTimePredictor", 1, model, "reproduced_from_training_split", None)


def serving_features(events: pd.DataFrame) -> pd.DataFrame:
    """The API's cold-start features, computed from the timestamp the client sent."""
    frame = pd.DataFrame({
        "segment_id": events["segment_id"].astype(str).to_numpy(),
        "direction": events["direction"].astype(str).to_numpy(),
        "segment_length_km": events["segment_length_km"].astype(float).to_numpy(),
        "route_id": events["route_id"].astype(str).to_numpy(),
        "t_entry": events["entry_ts_sent"].astype(float).to_numpy(),
    }, index=events.index)
    return engineer_features(frame, use_observed_history=False)


def period_of(hours: pd.Series, periods: list[dict]) -> pd.Series:
    labels = pd.Series(index=hours.index, dtype=object)
    for period in periods:
        labels[(hours >= period["start_hour"]) & (hours < period["end_hour"])] = period["name"]
    return labels


def score(events: pd.DataFrame, handle: ModelHandle, periods: list[dict]) -> pd.DataFrame:
    features = serving_features(events)
    predictions = np.asarray(handle.model.predict(features[FEATURES]), dtype=float)
    if not np.isfinite(predictions).all() or (predictions <= 0).any():
        raise ValueError("The model returned an invalid duration during replay.")
    scored = events.copy()
    for column in ("minute_of_day", "rush_hour_cat", "entry_hour"):
        scored[column] = features[column].to_numpy()
    received_hour = pd.to_datetime(scored["received_at"] + 19800, unit="s", utc=True).dt.hour
    scored["service_date"] = pd.to_datetime(scored["received_at"] + 19800, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    scored["period"] = period_of(received_hour, periods)
    scored["prediction_minutes"] = predictions
    scored["residual_minutes"] = scored["actual_minutes"] - predictions
    scored["abs_error_minutes"] = scored["residual_minutes"].abs()
    scored["model_version"] = handle.version
    return scored


@dataclass
class References:
    inputs: pd.DataFrame  # training requests with serving features, period and prediction
    segment_mae: dict[str, float]  # approved validation MAE per segment
    period_factor: dict[str, float]  # how much larger/smaller errors are in each period
    pooled_mae: float
    min_expected_error: float
    normalized_errors: np.ndarray  # validation errors / expected error, capped, in label-arrival order
    quality: QualityReference
    validation_scored: pd.DataFrame


def build_references(training: pd.DataFrame, validation: pd.DataFrame, handle: ModelHandle, policy: dict) -> References:
    """In-control references: training inputs, and the approved validation error profile."""
    periods = policy["periods"]
    config = policy["performance_detector"]
    inputs = score(base_events(training), handle, periods)
    validation_scored = score(base_events(validation), handle, periods)
    segment_mae = {str(k): float(v) for k, v in validation_scored.groupby("segment_id")["abs_error_minutes"].mean().items()}
    pooled = float(validation_scored["abs_error_minutes"].mean())
    # Errors are naturally larger at midday than at dawn; a period factor keeps the reference
    # day itself in control instead of flagging every congested afternoon.
    ratio = validation_scored["abs_error_minutes"] / validation_scored["segment_id"].map(segment_mae)
    period_factor = {str(k): float(v) for k, v in ratio.groupby(validation_scored["period"]).mean().items()}
    refs = References(inputs, segment_mae, period_factor, pooled, float(config["min_expected_error_minutes"]),
                      np.array([]), QualityReference.from_training(training), validation_scored)
    ordered = validation_scored.sort_values(["label_at", "event_id"], kind="stable")
    refs.normalized_errors = normalize_errors(ordered, refs, config["error_cap"])
    return refs


def expected_error(scored: pd.DataFrame, refs: References) -> np.ndarray:
    scale = scored["segment_id"].map(refs.segment_mae).fillna(refs.pooled_mae).to_numpy(dtype=float)
    factor = scored["period"].map(refs.period_factor).fillna(1.0).to_numpy(dtype=float)
    return np.maximum(scale * factor, refs.min_expected_error)


def normalize_errors(scored: pd.DataFrame, refs: References, cap: float) -> np.ndarray:
    """|error| divided by the error expected for that segment and period under approval conditions."""
    return np.minimum(scored["abs_error_minutes"].to_numpy(dtype=float) / expected_error(scored, refs), cap)


def _seed(*parts: str) -> int:
    return RANDOM_SEED + zlib.crc32("|".join(parts).encode())


def monitor_windows(scored: pd.DataFrame, refs: References, policy: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare each (service day, period) window with the same period of the reference."""
    limits = policy["thresholds"]
    common = dict(iterations=limits["bootstrap_iterations"], warn_quantile=limits["warn_quantile"],
                  alert_quantile=limits["alert_quantile"])
    monitored = [(name, "categorical") for name in policy["monitored_features"]["categorical"]]
    monitored += [(name, "numeric") for name in policy["monitored_features"]["numeric"]]
    ref_days = max(1, refs.inputs["service_date"].nunique())
    period_order = {period["name"]: position for position, period in enumerate(policy["periods"])}
    flags = request_flags(scored, refs.quality, skew_minutes=limits["timestamp_skew_minutes"])
    detector = policy["performance_detector"]
    normalized = normalize_errors(scored, refs, detector["error_cap"])

    window_rows, feature_rows = [], []
    for (day, period), window in scored.groupby(["service_date", "period"], sort=False):
        key = f"{day}|{period}"
        reference = refs.inputs[refs.inputs["period"] == period]
        quality = summarize_quality(flags.loc[window.index], alert_rate=limits["data_quality_alert_rate"])
        row = {
            "window": f"{day} {period}", "service_date": day, "period": period,
            "period_order": period_order[period],
            "window_start": float(window["received_at"].min()), "window_end": float(window["received_at"].max()),
            "labels_complete_at": float(window["label_at"].max()),
            "requests": len(window), "reference_requests_per_day": len(reference) / ref_days,
            "injected_requests": int(window["injected"].sum()),
            "mae_minutes": float(window["abs_error_minutes"].mean()),
            "bias_minutes": float(window["residual_minutes"].mean()),
            "mean_prediction_minutes": float(window["prediction_minutes"].mean()),
            "mean_actual_minutes": float(window["actual_minutes"].mean()),
            "data_quality_status": quality["status"], "data_quality_problem_rate": quality["any_problem_rate"],
            **{f"dq_{name}_rate": value for name, value in quality["rates"].items()},
        }
        enough = len(window) >= limits["min_window_requests"] and len(reference) > 0
        input_status = "INSUFFICIENT_DATA" if not enough else "OK"
        if enough:
            for feature, kind in monitored:
                result = calibrated_psi(reference[feature], window[feature], kind=kind, bins=limits["psi_bins"],
                                        seed=_seed(key, feature), **common)
                feature_rows.append({"window": row["window"], "service_date": day, "period": period,
                                     "feature": feature, "kind": kind, "psi": result.statistic,
                                     "warn_threshold": result.warn_threshold, "alert_threshold": result.alert_threshold,
                                     "null_exceedance": result.null_exceedance, "ks_pvalue": result.ks_pvalue,
                                     "status": result.status, "detected_at": row["window_end"]})
                if SEVERITY_RANK[result.status] > SEVERITY_RANK[input_status]:
                    input_status = result.status
            prediction = calibrated_psi(reference["prediction_minutes"], window["prediction_minutes"], kind="numeric",
                                        bins=limits["psi_bins"], seed=_seed(key, "prediction"), **common)
            row.update(prediction_psi=prediction.statistic, prediction_alert_threshold=prediction.alert_threshold,
                       prediction_drift_status=prediction.status)
        else:
            row.update(prediction_psi=np.nan, prediction_alert_threshold=np.nan, prediction_drift_status="INSUFFICIENT_DATA")
        row["input_drift_status"] = input_status
        if len(window) >= limits["min_window_labels"]:
            perf = calibrated_mean_shift(refs.normalized_errors, normalized[scored.index.get_indexer(window.index)],
                                         seed=_seed(key, "performance"), block_length=detector["block_length"], **common)
            row.update(normalized_error=perf.statistic, performance_alert_threshold=perf.alert_threshold,
                       performance_status=perf.status)
        else:
            row.update(normalized_error=np.nan, performance_alert_threshold=np.nan, performance_status="INSUFFICIENT_DATA")
        window_rows.append(row)
    windows = pd.DataFrame(window_rows).sort_values(["service_date", "period_order"]).reset_index(drop=True)
    return windows, pd.DataFrame(feature_rows)


def run_cusum(scored: pd.DataFrame, refs: References, policy: dict, cache: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Sequential change detection on errors in the order labels arrive."""
    config = policy["performance_detector"]
    stream = scored.sort_values(["label_at", "event_id"], kind="stable").reset_index(drop=True)
    stream["normalized_error"] = normalize_errors(stream, refs, config["error_cap"])
    segments = sorted(stream["segment_id"].unique())
    detector_names = ["all_segments", *segments]
    alpha = config["family_false_alarm_rate"] / len(detector_names)

    def threshold(length: int) -> float:
        key = (length, alpha)
        if key not in cache:
            cache[key] = calibrate_cusum_threshold(refs.normalized_errors, length, target=config["target"],
                                                   slack=config["slack"], false_alarm_rate=alpha,
                                                   iterations=config["calibration_iterations"], seed=RANDOM_SEED,
                                                   block_length=config["block_length"])
        return cache[key]

    detectors = {"all_segments": Cusum(config["target"], config["slack"], threshold(len(stream)))}
    for segment in segments:
        detectors[segment] = Cusum(config["target"], config["slack"], threshold(int((stream["segment_id"] == segment).sum())))
    rows, alarms = [], []
    for position, event in stream.iterrows():
        row = {"label_order": position, "event_id": event["event_id"], "label_at": event["label_at"],
               "segment_id": event["segment_id"], "normalized_error": event["normalized_error"],
               "abs_error_minutes": event["abs_error_minutes"], "injected": bool(event["injected"])}
        for name in ("all_segments", event["segment_id"]):
            detector = detectors[name]
            fired = detector.update(event["normalized_error"])
            column = "all" if name == "all_segments" else "segment"
            row[f"cusum_{column}"] = detector.value
            row[f"threshold_{column}"] = detector.threshold
            if fired:
                alarms.append({"detector": name, "label_order": position, "detected_at": float(event["label_at"]),
                               "event_id": event["event_id"], "statistic": detector.value,
                               "threshold": detector.threshold})
        rows.append(row)
    return pd.DataFrame(rows), alarms


def streaming_quality(scored: pd.DataFrame, refs: References, policy: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Per-request validation with a rolling failure rate, so a broken feed is caught within minutes."""
    limits = policy["thresholds"]
    flags = request_flags(scored, refs.quality, skew_minutes=limits["timestamp_skew_minutes"])
    ordered = scored.sort_values(["received_at", "event_id"], kind="stable")
    failing = flags.loc[ordered.index].any(axis=1).astype(int)
    rate = failing.rolling(limits["dq_rolling_requests"], min_periods=limits["dq_rolling_requests"]).mean()
    alarms = []
    breach = rate[rate > limits["data_quality_alert_rate"]]
    if not breach.empty:
        index = breach.index[0]
        alarms.append({"detector": f"rolling data quality (last {limits['dq_rolling_requests']} requests)",
                       "detected_at": float(scored.loc[index, "received_at"]), "event_id": scored.loc[index, "event_id"],
                       "statistic": float(breach.iloc[0]), "threshold": limits["data_quality_alert_rate"]})
    return flags, alarms


def collect_alerts(scenario: str, windows: pd.DataFrame, features: pd.DataFrame, alarms: list[dict],
                   quality_alarms: list[dict] | None = None) -> list[dict]:
    alerts = []
    for alarm in quality_alarms or []:
        alerts.append({"scenario": scenario, "type": "data_quality", "severity": "ALERT", "scope": alarm["detector"],
                       "detected_at": alarm["detected_at"], "statistic": alarm["statistic"], "threshold": alarm["threshold"],
                       "detail": f"{alarm['statistic']:.0%} of the latest requests failed validation"})
    for _, item in features[features["status"] != "OK"].iterrows() if not features.empty else []:
        alerts.append({"scenario": scenario, "type": "input_drift", "severity": item["status"],
                       "scope": f"{item['window']} · {item['feature']}", "detected_at": item["detected_at"],
                       "statistic": item["psi"], "threshold": item["alert_threshold"] if item["status"] == "ALERT" else item["warn_threshold"],
                       "detail": f"PSI {item['psi']:.3f} (alert above {item['alert_threshold']:.3f})"})
    for _, window in windows.iterrows():
        if window["prediction_drift_status"] in ("WARN", "ALERT"):
            alerts.append({"scenario": scenario, "type": "prediction_drift", "severity": window["prediction_drift_status"],
                           "scope": window["window"], "detected_at": window["window_end"],
                           "statistic": window["prediction_psi"], "threshold": window["prediction_alert_threshold"],
                           "detail": f"Prediction PSI {window['prediction_psi']:.3f}"})
        if window["data_quality_status"] in ("WARN", "ALERT"):
            alerts.append({"scenario": scenario, "type": "data_quality", "severity": window["data_quality_status"],
                           "scope": window["window"], "detected_at": window["window_end"],
                           "statistic": window["data_quality_problem_rate"], "threshold": None,
                           "detail": f"{window['data_quality_problem_rate']:.0%} of requests failed a data-quality check"})
        if window["performance_status"] in ("WARN", "ALERT"):
            alerts.append({"scenario": scenario, "type": "performance", "severity": window["performance_status"],
                           "scope": window["window"], "detected_at": window["labels_complete_at"],
                           "statistic": window["normalized_error"], "threshold": window["performance_alert_threshold"],
                           "detail": f"MAE {window['mae_minutes']:.2f} min, {window['normalized_error']:.2f}x the approved error level"})
    for alarm in alarms:
        alerts.append({"scenario": scenario, "type": "performance", "severity": "ALERT",
                       "scope": f"CUSUM · {alarm['detector']}", "detected_at": alarm["detected_at"],
                       "statistic": alarm["statistic"], "threshold": alarm["threshold"],
                       "detail": f"Sequential error detector crossed its threshold after {alarm['label_order'] + 1} labels"})
    for alert in alerts:
        alert["detected_at_ist"] = ist_text(alert["detected_at"])
    return sorted(alerts, key=lambda alert: (alert["detected_at"], -SEVERITY_RANK[alert["severity"]]))


def summarize(scenario: str, params: dict, scored: pd.DataFrame, windows: pd.DataFrame, alerts: list[dict],
              alarms: list[dict], policy: dict) -> dict:
    # Delay is measured from the first request the change actually touched: a midnight onset
    # with no buses until dawn should not count the empty night as detection time.
    injected = scored.loc[scored["injected"].astype(bool), "received_at"]
    onset = float(injected.min()) if not injected.empty else (
        datetime.fromisoformat(params["onset_ist"]).timestamp() if "onset_ist" in params else None)
    by_type = {}
    for alert in alerts:
        counts = by_type.setdefault(alert["type"], {"WARN": 0, "ALERT": 0})
        counts[alert["severity"]] += 1
    first_alert, delay = {}, {}
    for alert in alerts:
        if alert["severity"] != "ALERT" or (onset is not None and alert["detected_at"] < onset):
            continue
        if alert["type"] not in first_alert:
            first_alert[alert["type"]] = {k: alert[k] for k in ("detected_at", "detected_at_ist", "scope", "detail")}
            if onset is not None:
                delay[alert["type"]] = round((alert["detected_at"] - onset) / 60.0, 1)
    daily = scored.groupby("service_date").agg(requests=("event_id", "size"), mae_minutes=("abs_error_minutes", "mean"),
                                               bias_minutes=("residual_minutes", "mean")).reset_index()
    segment = scored.groupby(["service_date", "segment_id"]).agg(
        requests=("event_id", "size"), mae_minutes=("abs_error_minutes", "mean"),
        bias_minutes=("residual_minutes", "mean")).reset_index()
    actions = [policy["runbook"][kind] for kind in ("data_quality", "input_drift", "prediction_drift", "performance")
               if by_type.get(kind, {}).get("ALERT")]
    return {
        "scenario": scenario, "title": params.get("title", scenario), "description": params.get("description", ""),
        "onset_ist": params.get("onset_ist"), "first_affected_ist": ist_text(onset) if onset is not None else None,
        "requests": int(len(scored)), "injected_requests": int(scored["injected"].sum()),
        "alerts_by_type": by_type, "first_alert_after_onset": first_alert, "detection_delay_minutes": delay,
        "cusum_alarms": [{**alarm, "detected_at_ist": ist_text(alarm["detected_at"])} for alarm in alarms],
        "daily": daily.to_dict(orient="records"), "segments": segment.to_dict(orient="records"),
        "windows_with_alerts": int(((windows[["input_drift_status", "prediction_drift_status", "data_quality_status",
                                              "performance_status"]] == "ALERT").any(axis=1)).sum()),
        "recommended_actions": actions,
    }


def run_replay(traversals_path: Path, handle: ModelHandle, output_dir: Path, *, policy_path: Path = DEFAULT_POLICY,
               scenarios: list[str] | None = None, splits=None) -> dict:
    policy = load_policy(policy_path)
    training, validation, test = splits if splits is not None else load_splits(traversals_path, policy)
    refs = build_references(training, validation, handle, policy)
    stream = base_events(pd.concat([validation, test]))
    names = scenarios or list(policy["scenarios"])
    output_dir.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    report = {
        "generated_at_utc": datetime.now().astimezone().isoformat(timespec="seconds"),
        "kind": "historical_replay",
        "note": "Replay of held-out 2019 traversals. Scenarios other than 'natural' contain clearly labelled injected changes.",
        "model": {"name": handle.name, "version": handle.version, "source": handle.source, "sha256": handle.sha256},
        "inputs": {"traversals_sha256": file_sha256(traversals_path) if traversals_path.exists() else None,
                   "policy_sha256": file_sha256(policy_path), "policy_version": policy["policy_version"]},
        "reference": {"training_requests": len(refs.inputs), "validation_requests": len(refs.validation_scored),
                      "approved_validation_mae": refs.pooled_mae, "segment_mae": refs.segment_mae,
                      "period_factor": refs.period_factor, "min_expected_error_minutes": refs.min_expected_error,
                      "quality": {"min_hour": refs.quality.min_hour, "max_hour": refs.quality.max_hour,
                                  "routes_by_segment": {k: sorted(v) for k, v in refs.quality.routes_by_segment.items()}}},
        "scenarios": {},
    }
    refs.inputs.to_csv(output_dir / "reference_requests.csv", index=False)
    for name in names:
        params = policy["scenarios"][name]
        events = apply_scenario(stream, name, params, seed=RANDOM_SEED)
        scored = score(events, handle, policy["periods"])
        windows, features = monitor_windows(scored, refs, policy)
        cusum, alarms = run_cusum(scored, refs, policy, cache)
        flags, quality_alarms = streaming_quality(scored, refs, policy)
        scored = scored.join(flags.add_prefix("dq_"))
        alerts = collect_alerts(name, windows, features, alarms, quality_alarms)
        summary = summarize(name, params, scored, windows, alerts, alarms, policy)
        folder = output_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        scored.to_csv(folder / "events.csv", index=False)
        windows.to_csv(folder / "windows.csv", index=False)
        features.to_csv(folder / "feature_drift.csv", index=False)
        cusum.to_csv(folder / "cusum.csv", index=False)
        (folder / "alerts.json").write_text(json.dumps(alerts, indent=2, default=float) + "\n", encoding="utf-8")
        (folder / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n", encoding="utf-8")
        report["scenarios"][name] = summary
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, default=float) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traversals", type=Path, default=DEFAULT_TRAVERSALS)
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR / "phase3" / "monitoring")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--reproduce-v1", action="store_true",
                        help="Refit v1's configuration instead of loading the approved bundle (records the substitution).")
    args = parser.parse_args()
    policy = load_policy(args.policy)
    splits = load_splits(args.traversals, policy)
    handle = reproduce_v1(splits[0]) if args.reproduce_v1 else load_approved_v1(args.bundle_dir)
    report = run_replay(args.traversals, handle, args.output_dir, policy_path=args.policy,
                        scenarios=args.scenarios, splits=splits)
    for name, summary in report["scenarios"].items():
        print(f"{name}: alerts={summary['alerts_by_type']} first={ {k: v['detected_at_ist'] for k, v in summary['first_alert_after_onset'].items()} }")


if __name__ == "__main__":
    main()
