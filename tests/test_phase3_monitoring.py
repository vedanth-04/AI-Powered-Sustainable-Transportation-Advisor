"""Phase 3 drift statistics, scenario injection, data-quality checks and the historical replay."""

from datetime import datetime
import json

import numpy as np
import pandas as pd
import pytest

from src.monitoring.drift import (Cusum, block_indices, calibrate_cusum_threshold, calibrated_mean_shift,
                                  calibrated_psi, psi)
from src.monitoring.quality import QualityReference, request_flags
from src.monitoring.replay import load_policy, load_splits, reproduce_v1, run_replay
from src.monitoring.scenarios import apply_scenario, base_events
from tests.phase3_fixtures import fast_policy, synthetic_traversals


def test_psi_is_zero_for_identical_samples_and_grows_with_shift():
    rng = np.random.default_rng(0)
    reference = rng.normal(0, 1, 2000)
    assert psi(reference, reference, kind="numeric") == pytest.approx(0.0, abs=1e-9)
    assert psi(reference, reference + 2.0, kind="numeric") > 1.0
    assert psi(["a"] * 50 + ["b"] * 50, ["a"] * 90 + ["c"] * 10, kind="categorical") > 0.25


def test_calibrated_psi_respects_sample_size():
    rng = np.random.default_rng(1)
    reference = rng.choice(["A", "B", "C", "D"], 400)
    in_control = calibrated_psi(reference, rng.choice(reference, 30), kind="categorical", iterations=300)
    shifted = calibrated_psi(reference, ["A"] * 27 + ["B"] * 3, kind="categorical", iterations=300)
    assert in_control.status in ("OK", "WARN")
    assert shifted.status == "ALERT" and shifted.statistic > shifted.alert_threshold
    numeric = calibrated_psi(rng.normal(0, 1, 400), rng.normal(3, 1, 30), kind="numeric", iterations=300)
    assert numeric.status == "ALERT" and numeric.ks_pvalue < 0.001


def test_mean_shift_and_cusum_detect_an_error_increase_but_not_in_control_noise():
    rng = np.random.default_rng(2)
    reference = rng.exponential(1.0, 300)
    assert calibrated_mean_shift(reference, rng.exponential(1.0, 40), iterations=300).status in ("OK", "WARN")
    assert calibrated_mean_shift(reference, rng.exponential(2.5, 40), iterations=300).status == "ALERT"
    threshold = calibrate_cusum_threshold(reference, 200, target=1.0, slack=0.5, false_alarm_rate=0.05, iterations=500)
    quiet = Cusum(1.0, 0.5, threshold)
    for value in rng.exponential(1.0, 200)[:100]:
        quiet.update(value)
    loud = Cusum(1.0, 0.5, threshold)
    stream = np.concatenate([rng.exponential(1.0, 100), rng.exponential(3.0, 100)])
    for value in stream:
        loud.update(value)
    assert loud.alarm_index is not None and loud.alarm_index >= 100
    assert quiet.alarm_index is None


def test_block_bootstrap_indices_wrap_and_keep_runs():
    indices = block_indices(10, 23, 8, np.random.default_rng(3))
    assert len(indices) == 23 and indices.min() >= 0 and indices.max() < 10
    assert all((indices[i + 1] - indices[i]) % 10 == 1 for i in range(7))


def test_scenarios_change_only_what_they_claim():
    policy = load_policy()
    events = base_events(synthetic_traversals())
    natural = apply_scenario(events, "natural", {}, seed=1)
    pd.testing.assert_frame_equal(natural, events)

    params = policy["scenarios"]["concept_drift"]
    drifted = apply_scenario(events, "concept_drift", params, seed=1)
    onset = datetime.fromisoformat(params["onset_ist"]).timestamp()
    hit = (drifted["received_at"] >= onset) & (drifted["segment_id"] == params["segment_id"])
    assert hit.any() and drifted.loc[hit, "injected"].all() and not drifted.loc[~hit, "injected"].any()
    np.testing.assert_allclose(drifted.loc[hit, "actual_minutes"], events.loc[hit, "actual_minutes"] * params["duration_multiplier"])
    np.testing.assert_allclose(drifted["label_at"], drifted["received_at"] + drifted["actual_minutes"] * 60)
    assert (drifted["entry_ts_sent"] == events["entry_ts_sent"]).all()

    faulty = apply_scenario(events, "data_quality", policy["scenarios"]["data_quality"], seed=1)
    assert set(faulty.loc[faulty["injected"], "injection"]) == {"timezone_shift", "unknown_route"}
    assert (faulty.loc[faulty["injection"] == "timezone_shift", "entry_ts_sent"]
            < faulty.loc[faulty["injection"] == "timezone_shift", "received_at"]).all()
    assert (faulty["actual_minutes"] == events["actual_minutes"]).all()

    shifted = apply_scenario(events, "covariate_shift", policy["scenarios"]["covariate_shift"], seed=1)
    assert len(shifted) == len(events)
    assert shifted.loc[shifted["injected"], "segment_id"].value_counts(normalize=True)["ORR_CHIRAG_TO_NEHRU_PLACE_EB"] > 0.4


def test_quality_flags_unseen_routes_bad_hours_and_clock_skew():
    training = synthetic_traversals()
    reference = QualityReference.from_training(training)
    requests = base_events(training).head(3).copy()
    requests.loc[1, "route_id"] = "90X"
    requests.loc[2, "entry_ts_sent"] -= 330 * 60
    flags = request_flags(requests, reference, skew_minutes=15)
    assert not flags.loc[0].any()
    assert flags.loc[1, "unseen_route"]
    assert flags.loc[2, "timestamp_skew"] and flags.loc[2, "outside_service_hours"]


def test_replay_writes_evidence_and_detects_injected_model_drift(tmp_path):
    traversals = synthetic_traversals()
    path = tmp_path / "traversals.csv"
    traversals.to_csv(path, index=False)
    policy_path = fast_policy(tmp_path)
    splits = load_splits(path, load_policy(policy_path))
    handle = reproduce_v1(splits[0])
    report = run_replay(path, handle, tmp_path / "monitoring", policy_path=policy_path,
                        scenarios=["natural", "concept_drift", "data_quality"], splits=splits)

    for scenario in ("natural", "concept_drift", "data_quality"):
        for name in ("events.csv", "windows.csv", "feature_drift.csv", "cusum.csv", "alerts.json", "summary.json"):
            assert (tmp_path / "monitoring" / scenario / name).exists()
    natural = report["scenarios"]["natural"]
    assert not natural["cusum_alarms"], "In-control synthetic data must not trigger the sequential detector."
    concept = report["scenarios"]["concept_drift"]
    assert any(alarm["detector"] in ("ORR_CHIRAG_TO_NEHRU_PLACE_EB", "all_segments") for alarm in concept["cusum_alarms"])
    assert concept["detection_delay_minutes"]["performance"] >= 0
    quality = report["scenarios"]["data_quality"]
    assert quality["alerts_by_type"]["data_quality"]["ALERT"] >= 1
    assert quality["detection_delay_minutes"]["data_quality"] < 120
    assert json.loads((tmp_path / "monitoring" / "report.json").read_text())["kind"] == "historical_replay"
