"""Phase 3 model lifecycle: drift-triggered retraining, gated promotion, rollback drill, export.

Version 1 is the approved Phase 2 model. A performance alarm from the monitoring replay
opens a retraining candidate (version 2). A candidate trained on a corrupted batch
(version 3) demonstrates that the gate keeps a bad model away from serving.
"""

from __future__ import annotations

from datetime import date, datetime, time
from hashlib import sha256
from importlib.metadata import version as package_version
from io import BytesIO
import json
from pathlib import Path
from platform import python_version
import subprocess

import joblib
import numpy as np
import pandas as pd

from src.config import MLFLOW_REGISTERED_MODEL_NAME, PROJECT_ROOT
from src.features.build_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, TARGET_COLUMN
from src.features.label_generation import IST_OFFSET
from src.models.evaluate import compute_regression_metrics
from src.monitoring.replay import ModelHandle, base_events, serving_features
from src.versioning.gate import promotion_checks, segment_comparison, validate_training_data
from src.versioning.ledger import Ledger, diff_versions, verify_audit_chain

FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
DEFAULT_PROMOTION_POLICY = PROJECT_ROOT / "config" / "phase3" / "promotion_policy.json"
DEMO_REQUEST = {"segment_id": "ORR_CHIRAG_TO_NEHRU_PLACE_EB", "route_id": "90", "entry_at": "2019-07-08T17:10:00+05:30"}
HYPERPARAMETERS = ("n_estimators", "max_depth", "learning_rate", "subsample", "random_state")


def plain(value):
    """JSON-safe copy (numpy scalars become Python numbers)."""
    return json.loads(json.dumps(value, default=lambda item: item.item() if hasattr(item, "item") else str(item)))


def code_identity() -> dict:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True, timeout=10).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, text=True, timeout=10).strip())
        return {"git_head": head, "worktree_dirty": dirty}
    except Exception:
        return {"git_head": None, "worktree_dirty": None}


def runtime() -> dict:
    return {"python": python_version(), **{name: package_version(name) for name in ("scikit-learn", "pandas", "numpy")}}


def ist_dates(frame: pd.DataFrame) -> list[str]:
    return sorted(pd.to_datetime(frame["t_entry"] + 19800, unit="s", utc=True).dt.strftime("%Y-%m-%d").unique().tolist())


def frame_sha256(frame: pd.DataFrame) -> str:
    return sha256(frame.sort_values(["t_entry", "segment_id"]).to_csv(index=False).encode()).hexdigest()


def holdout_split(traversals: pd.DataFrame, holdout_start: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = datetime.combine(holdout_start, time.min, tzinfo=IST_OFFSET).timestamp()
    return traversals[traversals["t_exit"] < cutoff].copy(), traversals[traversals["t_entry"] >= cutoff].copy()


def fit_model(name: str, traversals: pd.DataFrame):
    from src.models.train import build_candidate_models

    model = build_candidate_models()[name]
    events = base_events(traversals)
    model.fit(serving_features(events)[FEATURES], events["actual_minutes"])
    return model


def predict(model, traversals: pd.DataFrame) -> np.ndarray:
    """Predictions in the row order of `traversals` (base_events sorts by time internally)."""
    events = base_events(traversals)
    values = np.asarray(model.predict(serving_features(events)[FEATURES]), dtype=float)
    return pd.Series(values, index=events["source_row"].to_numpy()).reindex(traversals.index).to_numpy()


def hyperparameters(model) -> dict:
    params = model.get_params()
    return {key: params.get(f"regressor__{key}") for key in HYPERPARAMETERS}


def corrupt_like_feed_fault(traversals: pd.DataFrame, day: str, params: dict, seed: int) -> pd.DataFrame:
    """Replay the monitoring scenario's timezone/route fault on one stored training day."""
    out = traversals.copy()
    on_day = np.flatnonzero((pd.to_datetime(out["t_entry"] + 19800, unit="s", utc=True).dt.strftime("%Y-%m-%d") == day).to_numpy())
    draws = np.random.default_rng(seed).random(len(on_day))
    tz_rows = out.index[on_day[draws < params["timezone_fault_fraction"]]]
    route_rows = out.index[on_day[(draws >= params["timezone_fault_fraction"])
                                  & (draws < params["timezone_fault_fraction"] + params["unknown_route_fraction"])]]
    shift = float(params["timezone_shift_minutes"]) * 60.0
    out.loc[tz_rows, ["t_entry", "t_exit"]] += shift
    out.loc[route_rows, "route_id"] = str(params["unknown_route_id"])
    return out


class Lifecycle:
    def __init__(self, output_dir: Path, traversals: pd.DataFrame, traversals_sha256: str | None,
                 promotion_policy: dict, monitoring_policy: dict, actor: str | None = None):
        self.output_dir = output_dir
        self.registry_dir = output_dir / "registry"
        self.traversals = traversals
        self.traversals_sha256 = traversals_sha256
        self.policy = promotion_policy
        self.monitoring_policy = monitoring_policy
        self.actor = actor
        holdout_start = date.fromisoformat(promotion_policy["retraining_window"]["promotion_holdout_start_ist"])
        self.retrain_window, self.holdout = holdout_split(traversals, holdout_start)
        self.ledger = Ledger.create(self.registry_dir / "model_versions.json", MLFLOW_REGISTERED_MODEL_NAME)
        self.models: dict[int, object] = {}
        self.holdout_predictions = pd.DataFrame({
            "received_at": self.holdout["t_entry"].to_numpy(), "segment_id": self.holdout["segment_id"].astype(str).to_numpy(),
            "route_id": self.holdout["route_id"].astype(str).to_numpy(),
            "actual_minutes": self.holdout[TARGET_COLUMN].to_numpy()})

    # ----- helpers ---------------------------------------------------------------------------
    def _store_artifact(self, version: int, model, original_bytes: bytes | None = None) -> dict:
        folder = self.registry_dir / f"v{version}"
        folder.mkdir(parents=True, exist_ok=True)
        if original_bytes is None:
            buffer = BytesIO()
            joblib.dump(model, buffer)
            original_bytes = buffer.getvalue()
        (folder / "model.joblib").write_bytes(original_bytes)
        return {"path": f"registry/v{version}/model.joblib", "sha256": sha256(original_bytes).hexdigest(),
                "bytes": len(original_bytes)}

    def _evaluate(self, model) -> tuple[np.ndarray, dict, dict]:
        predictions = predict(model, self.holdout)
        metrics = compute_regression_metrics(self.holdout[TARGET_COLUMN], predictions)
        by_segment = (self.holdout.assign(error=np.abs(predictions - self.holdout[TARGET_COLUMN].to_numpy()))
                      .groupby("segment_id")["error"].mean().to_dict())
        return predictions, metrics, by_segment

    def _record(self, *, change_type: str, reason: str, trigger: dict, parent: int | None, training: pd.DataFrame,
                model, artifact: dict | None, metrics: dict | None, by_segment: dict | None, status: str,
                source: str, extra: dict | None = None) -> dict:
        from src.api.bundle import feature_schema_sha256

        return plain({
            "status": status, "change_type": change_type, "reason": reason, "trigger": trigger,
            "parent_version": parent, "source": source,
            "training_window": {"dates_ist": ist_dates(training), "rows": len(training),
                                "rows_sha256": frame_sha256(training)},
            "data": {"input_sha256": self.traversals_sha256},
            "algorithm": type(model.named_steps["regressor"]).__name__ if hasattr(model, "named_steps") else type(model).__name__,
            "hyperparameters": hyperparameters(model) if hasattr(model, "named_steps") else {},
            "features": FEATURES, "history_policy": "cold_start_v1",
            "feature_schema_sha256": feature_schema_sha256(),
            "code": code_identity(), "runtime": runtime(), "artifact": artifact,
            "holdout": {"dates_ist": ist_dates(self.holdout), "rows": len(self.holdout)},
            "holdout_metrics": metrics, "holdout_mae_by_segment": by_segment, **(extra or {}),
        })

    # ----- lifecycle steps ---------------------------------------------------------------------
    def register_v1(self, handle: ModelHandle, original_bytes: bytes | None, v1_training: pd.DataFrame) -> dict:
        artifact = self._store_artifact(1, handle.model, original_bytes)
        if handle.sha256 and artifact["sha256"] != handle.sha256:
            raise ValueError("The stored v1 artifact differs from the approved bundle hash.")
        predictions, metrics, by_segment = self._evaluate(handle.model)
        self.holdout_predictions["pred_v1"] = predictions
        reason = ("Phase 2 approved release, imported unchanged by artifact hash. It is the serving baseline that "
                  "Phase 3 monitors." if handle.source == "approved_bundle" else
                  "Reproduction of the Phase 2 v1 configuration on its original training split (approved bundle not available here).")
        record = self._record(change_type="initial_release", reason=reason,
                              trigger={"type": "phase2_approval", "evidence": "docs/results/phase2-v1/quality_report.json"},
                              parent=None, training=v1_training, model=handle.model, artifact=artifact, metrics=metrics,
                              by_segment=by_segment, status="approved", source=handle.source)
        record = self.ledger.add_version(record, actor=self.actor)
        self.models[1] = handle.model
        self.ledger.promote(1, reason="Phase 2 approved model serves at the start of Phase 3.", actor=self.actor)
        return record

    def retrain_candidate(self, *, change_type: str, reason: str, trigger: dict, training: pd.DataFrame,
                          parent: int, quarantine: bool = False) -> dict:
        champion_version = self.ledger.aliases["champion"]
        champion = self.models[champion_version]
        validation = validate_training_data(training, self.policy)
        model = fit_model("Gradient Boosting Regressor", training)
        baseline = fit_model("Historical-Median Baseline", training)
        candidate_pred, metrics, by_segment = self._evaluate(model)
        champion_pred, champion_metrics, _ = self._evaluate(champion)
        baseline_pred, baseline_metrics, _ = self._evaluate(baseline)
        buffer = BytesIO()
        joblib.dump(model, buffer)
        reloaded = joblib.load(BytesIO(buffer.getvalue()))
        reload_diff = float(np.max(np.abs(predict(reloaded, self.holdout) - candidate_pred)))
        from src.api.bundle import feature_schema_sha256

        gate = promotion_checks(
            data_validation=validation, candidate=metrics, champion=champion_metrics, baseline=baseline_metrics,
            segment_table=segment_comparison(self.holdout, candidate_pred, champion_pred),
            schema_matches=list(getattr(model, "feature_names_in_", [])) == FEATURES and feature_schema_sha256() is not None,
            reload_max_diff=reload_diff,
            predictions_valid=bool(np.isfinite(candidate_pred).all() and (candidate_pred > 0).all()),
            policy=self.policy)
        version = self.ledger.next_version()
        artifact = self._store_artifact(version, model, buffer.getvalue())
        record = self._record(
            change_type=change_type, reason=reason, trigger=trigger, parent=parent, training=training, model=model,
            artifact=artifact, metrics=metrics, by_segment=by_segment, status="candidate", source="phase3_retraining",
            extra={"data_validation": validation, "quarantined": quarantine,
                   "gate": {**gate, "compared_with": {"champion_version": champion_version,
                                                      "champion_metrics": champion_metrics,
                                                      "median_baseline_metrics": baseline_metrics}}})
        record = self.ledger.add_version(record, actor=self.actor)
        self.models[version] = model
        self.holdout_predictions[f"pred_v{version}"] = candidate_pred
        self.holdout_predictions[f"baseline_for_v{version}"] = baseline_pred
        failed = [check["name"] for check in gate["checks"] if not check["passed"]]
        if gate["passed"] and not quarantine:
            self.ledger.set_status(version, "approved", reason="Every promotion check passed.", actor=self.actor)
            self.ledger.promote(version, reason=f"v{version} beat champion v{champion_version} on the "
                                f"{record['holdout']['dates_ist'][0]} holdout ({gate['relative_mae_improvement']:+.1%} MAE).",
                                actor=self.actor)
        else:
            self.ledger.set_status(version, "rejected", reason="Failed: " + ", ".join(failed or ["quarantined batch"]),
                                   actor=self.actor)
        return self.ledger.get(version)

    def export_bundle(self, version: int) -> dict:
        """Write a serving bundle the existing FastAPI app can load (BUS_MODEL_BUNDLE_DIR)."""
        from sklearn import __version__ as sklearn_version
        from src.api.bundle import load_bundle

        record = self.ledger.get(version)
        folder = self.output_dir / "serving" / f"v{version}"
        folder.mkdir(parents=True, exist_ok=True)
        model_bytes = (self.output_dir / record["artifact"]["path"]).read_bytes()
        (folder / "model.joblib").write_bytes(model_bytes)
        manifest = {"model_name": MLFLOW_REGISTERED_MODEL_NAME, "model_version": version, "history_policy": "cold_start_v1",
                    "features": FEATURES, "model_sha256": sha256(model_bytes).hexdigest(),
                    "scikit_learn_version": sklearn_version, "segment_id": DEMO_REQUEST["segment_id"],
                    "route_id": DEMO_REQUEST["route_id"]}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        bundle = load_bundle(folder)
        return {"version": version, "path": f"serving/v{version}", "manifest_sha256": sha256((folder / "manifest.json").read_bytes()).hexdigest(),
                "demo_prediction_minutes": demo_prediction(bundle.model),
                "serve_command": f"$env:BUS_MODEL_BUNDLE_DIR='outputs/phase3/serving/v{version}'; python -m uvicorn src.api.main:app --port 8002"}

    def rollback_drill(self) -> dict:
        """Roll back to `previous`, prove it can serve, then roll forward again (all audited)."""
        champion = self.ledger.aliases["champion"]
        target = self.ledger.rollback(reason="Scheduled rollback drill: confirm the previous version can serve immediately.",
                                      actor=self.actor)
        record = self.ledger.get(target)
        stored = (self.output_dir / record["artifact"]["path"]).read_bytes()
        hash_ok = sha256(stored).hexdigest() == record["artifact"]["sha256"]
        prediction = demo_prediction(joblib.load(BytesIO(stored)))
        self.ledger.promote(champion, reason="Rollback drill complete; restore the approved champion.", actor=self.actor)
        return {"rolled_back_from": champion, "rolled_back_to": target, "artifact_hash_verified": hash_ok,
                "demo_prediction_minutes": prediction, "restored_champion": self.ledger.aliases["champion"],
                "passed": hash_ok and np.isfinite(prediction) and self.ledger.aliases["champion"] == champion}


def demo_prediction(model) -> float:
    entry = datetime.fromisoformat(DEMO_REQUEST["entry_at"]).timestamp()
    from src.features.segment_config import get_segment

    segment = get_segment(DEMO_REQUEST["segment_id"])
    events = pd.DataFrame([{"segment_id": segment.segment_id, "direction": segment.direction,
                            "segment_length_km": segment.length_km, "route_id": DEMO_REQUEST["route_id"],
                            "entry_ts_sent": entry}])
    return float(model.predict(serving_features(events)[FEATURES])[0])


def performance_trigger(monitoring_report: dict) -> dict | None:
    natural = monitoring_report["scenarios"].get("natural")
    if not natural or not natural["cusum_alarms"]:
        return None
    first = natural["cusum_alarms"][0]
    return {"type": "performance_drift", "scenario": "natural",
            "first_alarm_ist": first["detected_at_ist"], "detector": first["detector"],
            "alarms": [{"detector": a["detector"], "at_ist": a["detected_at_ist"]} for a in natural["cusum_alarms"]],
            "evidence": "outputs/phase3/monitoring/natural/alerts.json"}


def run_lifecycle(*, traversals: pd.DataFrame, traversals_sha256: str | None, output_dir: Path, v1: ModelHandle,
                  v1_bytes: bytes | None, v1_training: pd.DataFrame, monitoring_report: dict, monitoring_policy: dict,
                  promotion_policy_path: Path = DEFAULT_PROMOTION_POLICY, actor: str | None = None,
                  mlflow_sync: bool = True) -> dict:
    policy = json.loads(promotion_policy_path.read_text(encoding="utf-8"))
    life = Lifecycle(output_dir, traversals, traversals_sha256, policy, monitoring_policy, actor)
    life.register_v1(v1, v1_bytes, v1_training)
    trigger = performance_trigger(monitoring_report)
    report = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
              "promotion_policy_sha256": sha256(promotion_policy_path.read_bytes()).hexdigest(),
              "retraining_trigger": trigger}
    if trigger is None:
        report["decision"] = "No performance alarm in the natural replay; no retraining candidate was opened."
    else:
        life.retrain_candidate(
            change_type="data_refresh",
            reason=(f"Performance drift alarm ({trigger['detector']}, {trigger['first_alarm_ist']} IST). Retrained on every "
                    "complete labelled day before the holdout, with the v1 algorithm, features and hyperparameters unchanged."),
            trigger=trigger, training=life.retrain_window, parent=1)
        fault = monitoring_policy["scenarios"]["data_quality"]
        newest_day = ist_dates(life.retrain_window)[-1]
        corrupted = corrupt_like_feed_fault(life.retrain_window, newest_day, fault, seed=42)
        life.retrain_candidate(
            change_type="rejected_candidate",
            reason=(f"Drill: retraining attempted on a batch where the {newest_day} feed had the timezone/route fault "
                    "seen in the data-quality scenario. Trained only in quarantine to measure the harm the gate prevents."),
            trigger={"type": "data_quality_drill", "scenario": "data_quality", "corrupted_day": newest_day},
            training=corrupted, parent=life.ledger.aliases["champion"], quarantine=True)
    champion = life.ledger.aliases["champion"]
    report["export"] = life.export_bundle(champion)
    report["rollback_drill"] = life.rollback_drill() if "previous" in life.ledger.aliases else None
    if mlflow_sync:
        from src.versioning.mlflow_sync import sync_to_mlflow

        report["mlflow"] = sync_to_mlflow(life.ledger, life.registry_dir,
                                          serving_features(base_events(life.holdout))[FEATURES])
    else:
        report["mlflow"] = {"status": "skipped", "reason": "Disabled for this run."}
    for record in life.ledger.versions:
        record["mlflow"] = next((item for item in report["mlflow"].get("versions", []) if item["version"] == record["version"]), None)
    life.ledger.save()
    report["aliases"] = dict(life.ledger.aliases)
    report["versions"] = [{key: record.get(key) for key in ("version", "status", "change_type", "reason", "parent_version",
                                                            "training_window", "holdout_metrics", "artifact")}
                          for record in life.ledger.versions]
    report["version_diffs"] = {f"v{a['version']}->v{b['version']}": diff_versions(a, b)
                               for a, b in zip(life.ledger.versions, life.ledger.versions[1:])}
    report["gates"] = {f"v{record['version']}": record.get("gate") for record in life.ledger.versions if record.get("gate")}
    report["audit_chain"] = verify_audit_chain(life.ledger.audit_path)
    life.holdout_predictions.to_csv(life.registry_dir / "holdout_predictions.csv", index=False)
    (life.registry_dir / "lifecycle_report.json").write_text(json.dumps(plain(report), indent=2) + "\n", encoding="utf-8")
    return plain(report)
