"""Phase 3 version ledger, audit chain, promotion gate and the end-to-end lifecycle."""

import json

import numpy as np
import pandas as pd
import pytest

from src.api.bundle import load_bundle
from src.monitoring.replay import load_policy, load_splits, reproduce_v1, run_replay
from src.versioning.gate import promotion_checks, validate_training_data
from src.versioning.ledger import Ledger, diff_versions, read_audit, verify_audit_chain
from src.versioning.lifecycle import DEFAULT_PROMOTION_POLICY, corrupt_like_feed_fault, run_lifecycle
from tests.phase3_fixtures import fast_policy, synthetic_traversals

PROMOTION = json.loads(DEFAULT_PROMOTION_POLICY.read_text(encoding="utf-8"))


def _approved(**extra):
    return {"status": "approved", "change_type": "test", "reason": "unit test", **extra}


def test_ledger_promotion_rollback_and_tamper_evident_audit(tmp_path):
    ledger = Ledger.create(tmp_path / "model_versions.json")
    first = ledger.add_version(_approved(), actor="tester")
    ledger.promote(first["version"], reason="start", actor="tester")
    second = ledger.add_version({"status": "candidate", "change_type": "test", "reason": "retrain"}, actor="tester")
    with pytest.raises(ValueError):
        ledger.promote(second["version"], reason="not approved yet", actor="tester")
    ledger.set_status(second["version"], "approved", reason="gate passed", actor="tester")
    ledger.promote(second["version"], reason="better", actor="tester")
    assert ledger.aliases == {"champion": 2, "previous": 1}
    assert ledger.rollback(reason="drill", actor="tester") == 1
    assert Ledger.load(ledger.path).aliases == {"champion": 1, "previous": 2}

    assert verify_audit_chain(ledger.audit_path)["valid"]
    entries = read_audit(ledger.audit_path)
    assert [entry["action"] for entry in entries] == ["register_version", "promote", "register_version", "set_status",
                                                      "promote", "rollback"]
    entries[1]["reason"] = "edited later"
    ledger.audit_path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    assert verify_audit_chain(ledger.audit_path) == {"valid": False, "entries": 6, "broken_at_sequence": 2}
    with pytest.raises(FileExistsError):
        Ledger.create(ledger.path)


def test_data_validation_blocks_the_feed_fault():
    traversals = synthetic_traversals()
    assert validate_training_data(traversals, PROMOTION)["passed"]
    fault = load_policy()["scenarios"]["data_quality"]
    corrupted = corrupt_like_feed_fault(traversals, "2019-07-05", fault, seed=42)
    result = validate_training_data(corrupted, PROMOTION)
    failed = {check["name"] for check in result["checks"] if not check["passed"]}
    assert not result["passed"] and {"service_hours", "registered_segment_routes"} <= failed


def test_promotion_needs_every_rule():
    table = pd.DataFrame({"segment_id": ["A", "B"], "candidate_mae": [1.0, 2.5], "champion_mae": [1.2, 2.0]})
    kwargs = dict(data_validation={"passed": True, "checks": []}, champion={"mae_minutes": 2.0},
                  baseline={"mae_minutes": 3.0}, schema_matches=True, reload_max_diff=0.0, predictions_valid=True,
                  policy=PROMOTION)
    regressed = promotion_checks(candidate={"mae_minutes": 1.5}, segment_table=table, **kwargs)
    assert not regressed["passed"]
    assert [c["name"] for c in regressed["checks"] if not c["passed"]] == ["no_segment_regression"]
    fine = table.assign(candidate_mae=[1.0, 1.9])
    assert promotion_checks(candidate={"mae_minutes": 1.5}, segment_table=fine, **kwargs)["passed"]
    assert not promotion_checks(candidate={"mae_minutes": 1.99}, segment_table=fine, **kwargs)["passed"]


def test_diff_versions_reports_changed_fields():
    old = {"training_window": {"dates_ist": ["d1"], "rows": 1}, "algorithm": "GB", "artifact": {"sha256": "a"}}
    new = {"training_window": {"dates_ist": ["d1", "d2"], "rows": 2}, "algorithm": "GB", "artifact": {"sha256": "b"}}
    changed = {item["field"] for item in diff_versions(old, new) if item["changed"]}
    assert {"Training data window", "Training rows", "Artifact sha256"} <= changed and "Algorithm" not in changed


def test_lifecycle_promotes_a_better_candidate_rejects_the_corrupted_one_and_exports(tmp_path):
    traversals = synthetic_traversals(slow_last_day=1.35)
    path = tmp_path / "traversals.csv"
    traversals.to_csv(path, index=False)
    policy_path = fast_policy(tmp_path)
    policy = load_policy(policy_path)
    splits = load_splits(path, policy)
    handle = reproduce_v1(splits[0])
    monitoring = run_replay(path, handle, tmp_path / "phase3" / "monitoring", policy_path=policy_path,
                            scenarios=["natural"], splits=splits)
    if not monitoring["scenarios"]["natural"]["cusum_alarms"]:
        pytest.skip("Synthetic slowdown did not trigger the detector; nothing to retrain.")
    report = run_lifecycle(traversals=pd.concat(splits), traversals_sha256=None, output_dir=tmp_path / "phase3", v1=handle,
                           v1_bytes=None, v1_training=splits[0], monitoring_report=monitoring, monitoring_policy=policy,
                           actor="tester", mlflow_sync=False)

    statuses = {record["version"]: record["status"] for record in report["versions"]}
    assert statuses[1] == "approved" and statuses[3] == "rejected"
    assert report["gates"]["v3"]["checks"][0] == {**report["gates"]["v3"]["checks"][0], "name": "data_validation", "passed": False}
    champion = report["aliases"]["champion"]
    assert champion == (2 if statuses[2] == "approved" else 1)
    assert report["audit_chain"]["valid"]
    if report["rollback_drill"]:
        assert report["rollback_drill"]["passed"]
    bundle = load_bundle(tmp_path / "phase3" / "serving" / f"v{champion}")
    assert bundle.manifest.model_version == champion
    assert np.isfinite(report["export"]["demo_prediction_minutes"])
    ledger = Ledger.load(tmp_path / "phase3" / "registry" / "model_versions.json")
    assert ledger.aliases["champion"] == champion


def test_lifecycle_predictions_follow_input_row_order():
    from src.versioning.lifecycle import fit_model, predict

    traversals = synthetic_traversals()
    model = fit_model("Historical-Median Baseline", traversals)
    shuffled = traversals.sample(frac=1.0, random_state=3)
    expected = shuffled["segment_id"].map(model.segment_medians_).to_numpy()
    np.testing.assert_allclose(predict(model, shuffled), expected)
