"""System release registration: the advisor becomes a new version without moving the champion."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from src.versioning.ledger import Ledger, diff_versions, read_audit, verify_audit_chain
from src.versioning.release import (
    check, file_sha256, find_release, ledger_checks, register_release, release_gate,
)


def _ledger(tmp_path: Path) -> tuple[Ledger, Path]:
    registry = tmp_path / "phase3" / "registry"
    ledger = Ledger.create(registry / "model_versions.json")
    for version, status, payload in ((1, "approved", b"model-one"), (2, "candidate", b"model-two"), (3, "rejected", b"bad")):
        folder = registry / f"v{version}"
        folder.mkdir(parents=True)
        (folder / "model.joblib").write_bytes(payload)
        ledger.add_version({
            "status": status, "change_type": "data_refresh", "reason": f"v{version}", "algorithm": "GradientBoostingRegressor",
            "history_policy": "cold_start_v1", "training_window": {"dates_ist": ["2019-07-01"], "rows": 10},
            "holdout_metrics": {"mae_minutes": 3.0 + version}, "runtime": {"scikit-learn": "1.5.2"},
            "artifact": {"path": f"registry/v{version}/model.joblib", "sha256": sha256(payload).hexdigest()},
            "gate": {"passed": version != 3, "checks": []} if version > 1 else None})
    ledger.set_status(2, "approved", reason="gate passed")
    ledger.promote(1, reason="import")
    ledger.promote(2, reason="better")
    return ledger, registry


MANIFEST = {"kind": "system_release", "fingerprint": "f" * 64, "components": {"bus_model": {"ledger_version": 2}}}
PASSED = release_gate([check("advisor_tests_pass", True, "20 passed")])


def test_release_becomes_v4_with_the_champion_weights_and_its_own_alias(tmp_path):
    ledger, registry = _ledger(tmp_path)
    record = register_release(ledger, registry, MANIFEST, PASSED, expected_version=4)
    assert record["version"] == 4 and record["status"] == "approved" and record["change_type"] == "system_release"
    assert ledger.aliases == {"champion": 2, "previous": 1, "advisor": 4}
    assert record["artifact"]["sha256"] == ledger.get(2)["artifact"]["sha256"]
    assert (registry / "v4" / "model.joblib").read_bytes() == b"model-two"
    assert record["holdout_metrics"] == ledger.get(2)["holdout_metrics"] and record["parent_version"] == 2
    assert [e["action"] for e in read_audit(ledger.audit_path)[-3:]] == ["register_version", "set_status", "set_alias"]
    assert verify_audit_chain(ledger.audit_path)["valid"]
    reloaded = Ledger.load(registry / "model_versions.json")
    assert reloaded.aliases["advisor"] == 4 and reloaded.champion()["version"] == 2
    changed = {d["field"] for d in diff_versions(ledger.get(2), record) if d["changed"]}
    assert changed == {"System release fingerprint"}


def test_same_files_are_not_registered_twice(tmp_path):
    ledger, registry = _ledger(tmp_path)
    first = register_release(ledger, registry, MANIFEST, PASSED, expected_version=4)
    entries = len(read_audit(ledger.audit_path))
    again = register_release(ledger, registry, MANIFEST, PASSED, expected_version=4)
    assert again["version"] == first["version"] == 4 and len(ledger.versions) == 4
    assert len(read_audit(ledger.audit_path)) == entries and find_release(ledger, "f" * 64)["version"] == 4


def test_failed_gate_or_wrong_number_writes_nothing(tmp_path):
    ledger, registry = _ledger(tmp_path)
    entries = len(read_audit(ledger.audit_path))
    failed = release_gate([check("sample_delhi_plans", False, "no options")])
    with pytest.raises(ValueError, match="release gate failed"):
        register_release(ledger, registry, MANIFEST, failed, expected_version=4)
    with pytest.raises(ValueError, match="not v5"):
        register_release(ledger, registry, MANIFEST, PASSED, expected_version=5)
    assert len(ledger.versions) == 3 and len(read_audit(ledger.audit_path)) == entries
    assert not (registry / "v4").exists()


def test_champion_alias_cannot_be_moved_by_set_alias(tmp_path):
    ledger, _ = _ledger(tmp_path)
    with pytest.raises(ValueError, match="promote"):
        ledger.set_alias("champion", 3, reason="shortcut")
    assert ledger.aliases["champion"] == 2


def test_ledger_checks_catch_a_tampered_champion_artifact(tmp_path):
    ledger, registry = _ledger(tmp_path)
    assert all(c["passed"] for c in ledger_checks(ledger, registry))
    (registry / "v2" / "model.joblib").write_bytes(b"tampered")
    result = {c["name"]: c["passed"] for c in ledger_checks(ledger, registry)}
    assert result["bus_model_artifact_hash"] is False and result["audit_chain_valid"] is True


def test_text_hashes_ignore_windows_line_endings(tmp_path):
    lf, crlf = tmp_path / "a.py", tmp_path / "b.py"
    lf.write_bytes(b"x = 1\ny = 2\n")
    crlf.write_bytes(b"x = 1\r\ny = 2\r\n")
    assert file_sha256(lf) == file_sha256(crlf)
