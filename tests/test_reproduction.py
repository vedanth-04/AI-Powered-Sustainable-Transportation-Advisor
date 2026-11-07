"""Protect existing run directories and stop model operations after failed tests."""

import json
import subprocess
import sys
from datetime import date

import pytest

from scripts.reproduce_model_workflow import reproduce


def test_existing_directory_is_preserved_before_any_work(tmp_path, monkeypatch):
    traversals = tmp_path / "traversals.csv"
    traversals.write_text("existing input\n", encoding="utf-8")
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "tracking.db"
    sentinel.write_bytes(b"existing registry")

    def unexpected_operation(*args, **kwargs):
        pytest.fail("An existing output directory must be rejected before tests or model operations.")

    monkeypatch.setattr(subprocess, "run", unexpected_operation)
    with pytest.raises(FileExistsError):
        reproduce(traversals, date(2019, 7, 5), date(2019, 7, 8), output)
    assert sentinel.read_bytes() == b"existing registry"
    assert list(output.iterdir()) == [sentinel]


def test_failed_tests_stop_before_training_and_registry_creation(tmp_path, monkeypatch):
    traversals = tmp_path / "traversals.csv"
    traversals.write_text("input not reached\n", encoding="utf-8")
    output = tmp_path / "new-run"

    def failed_tests(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", failed_tests)
    with pytest.raises(subprocess.CalledProcessError):
        reproduce(traversals, date(2019, 7, 5), date(2019, 7, 8), output)
    report = json.loads((output / "workflow_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["stages"]["tests"]["status"] == "failed"
    assert not (output / "training").exists()
    assert not (output / "registry").exists()
    assert not (output / "serving").exists()


def test_dependency_failure_preserves_the_passing_test_stage(tmp_path, monkeypatch):
    traversals = tmp_path / "traversals.csv"
    traversals.write_text("input not reached\n", encoding="utf-8")
    output = tmp_path / "new-run"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "src.models.check_quality", None)
    with pytest.raises(ModuleNotFoundError):
        reproduce(traversals, date(2019, 7, 5), date(2019, 7, 8), output)
    report = json.loads((output / "workflow_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["stages"]["tests"]["status"] == "passed"
    assert report["stages"]["dependencies"]["status"] == "failed"
    assert not (output / "registry").exists()
