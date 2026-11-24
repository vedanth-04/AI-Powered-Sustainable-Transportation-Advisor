"""System releases: register what the Delhi advisor serves as one new model version.

A system release keeps the champion bus model's weights byte-for-byte and records, next to
them, the planner code, the pinned Delhi data snapshot, the fare and cab settings and the
web client. Registering it as a ledger version (and MLflow version) makes the advisor's whole
serving configuration traceable and comparable, the same way a retrained model is.

A release never moves the champion alias: the bus model API keeps serving the champion. It
gets its own `advisor` alias instead. Nothing is written unless every release-gate check passes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from src.versioning.ledger import Ledger, verify_audit_chain

RELEASE_ALIAS = "advisor"
TEXT_SUFFIXES = {".py", ".json", ".js", ".jsx", ".css", ".html", ".md", ".txt"}
DATA_FILES = ("network.npz", "network_meta.json", "places.json")
# The source groups that make up the advisor (paths relative to the repository root).
GROUPS = {
    "planner": ["advisor/*.py"],
    "config": ["advisor/config/advisor_config.json", "advisor/config/sources.json"],
    "web": ["advisor/web/index.html", "advisor/web/package.json", "advisor/web/vite.config.js", "advisor/web/src/**/*"],
    "scripts": ["scripts/advisor_*.py"],
}
NEVER_HASHED = {"advisor/config/local_settings.json"}  # private settings stay out of every manifest


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def file_sha256(path: Path) -> str:
    """Hash of a file; text files are hashed with LF line endings so Windows and Linux checkouts agree."""
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return sha256(data).hexdigest()


def source_group(root: Path, patterns: list[str]) -> dict:
    files = {}
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and rel not in NEVER_HASHED and "__pycache__" not in rel:
                files[rel] = file_sha256(path)
    combined = sha256("\n".join(f"{name} {digest}" for name, digest in sorted(files.items())).encode()).hexdigest()
    return {"sha256": combined, "files": files}


def build_manifest(root: Path, champion: dict) -> dict:
    """Everything the advisor serves with, as hashes plus the assumptions a reader needs."""
    config = json.loads((root / "advisor/config/advisor_config.json").read_text(encoding="utf-8"))
    sources = json.loads((root / "advisor/config/sources.json").read_text(encoding="utf-8"))["datasets"]
    data_dir = root / "data/processed/advisor"
    meta = json.loads((data_dir / "network_meta.json").read_text(encoding="utf-8"))
    components = {
        "bus_model": {
            "ledger_version": champion["version"], "artifact_sha256": champion["artifact"]["sha256"],
            "algorithm": champion["algorithm"], "history_policy": champion["history_policy"],
            "holdout_mae_minutes": champion["holdout_metrics"]["mae_minutes"],
            "applied_to_segment": config["bus_model"]["segment_id"],
            "source_order": config["bus_model"].get("sources"),
        },
        **{name: source_group(root, patterns) for name, patterns in GROUPS.items()},
    }
    data = {
        "snapshot": {name: {"sha256": file_sha256(data_dir / name), "bytes": (data_dir / name).stat().st_size}
                     for name in DATA_FILES},
        "counts": meta.get("counts"),
        "pinned_sources": {key: {"title": spec.get("title"), "mirror": spec.get("mirror"), "vintage": spec.get("vintage"),
                                 "files": len(spec.get("files", {}))} for key, spec in sources.items()},
    }
    assumptions = {key: config[key] for key in ("fares", "emissions_kg_per_pkm", "cab", "walking",
                                                "transfer_buffers_min", "router") if key in config}
    fingerprint = sha256(_canonical({
        "bus_model": components["bus_model"]["artifact_sha256"],
        "groups": {name: components[name]["sha256"] for name in GROUPS},
        "data": {name: item["sha256"] for name, item in data["snapshot"].items()},
    })).hexdigest()
    return {"kind": "system_release", "name": "Delhi multimodal sustainable transport advisor",
            "fingerprint": fingerprint, "components": components, "data": data, "assumptions": assumptions}


# ----- release gate -------------------------------------------------------------------------------

def check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def ledger_checks(ledger: Ledger, registry_dir: Path) -> list[dict]:
    chain = verify_audit_chain(ledger.audit_path)
    out = [check("audit_chain_valid", chain["valid"],
                 f"{chain['entries']} entries, hash chain intact" if chain["valid"]
                 else f"chain broken at entry {chain.get('broken_at_sequence')}")]
    champion = ledger.champion()
    if champion is None:
        return out + [check("bus_model_is_approved_champion", False, "the ledger has no champion")]
    gate_ok = bool((champion.get("gate") or {}).get("passed", champion["version"] == 1))
    out.append(check("bus_model_is_approved_champion", champion["status"] == "approved" and gate_ok,
                     f"v{champion['version']} is {champion['status']}; promotion gate "
                     f"{'passed' if gate_ok else 'not passed'}"))
    path = registry_dir.parent / champion["artifact"]["path"]
    actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    out.append(check("bus_model_artifact_hash", actual == champion["artifact"]["sha256"],
                     f"{champion['artifact']['path']} sha256 {'matches the ledger' if actual == champion['artifact']['sha256'] else 'does not match' if actual else 'file missing'}"))
    return out


def data_checks(root: Path) -> list[dict]:
    data_dir = root / "data/processed/advisor"
    missing = [name for name in DATA_FILES if not (data_dir / name).is_file()]
    if missing:
        return [check("data_snapshot_built_from_pins", False, f"missing {', '.join(missing)}; run scripts.advisor_build_network")]
    meta = json.loads((data_dir / "network_meta.json").read_text(encoding="utf-8"))
    sources = json.loads((root / "advisor/config/sources.json").read_text(encoding="utf-8"))["datasets"]
    pins = {f"{key}/{name}": digest for key, spec in sources.items() for name, digest in spec["files"].items()}
    differ = sorted(key for key, digest in pins.items() if meta.get("source_sha256", {}).get(key) != digest)
    return [check("data_snapshot_built_from_pins", not differ,
                  f"all {len(pins)} source files match their pinned sha256" if not differ
                  else f"{len(differ)} source files differ from their pins (first: {differ[0]})")]


def advisor_checks(champion_version: int) -> list[dict]:
    """Load the real network and planner offline, check the model source, parity and two Delhi trips."""
    from advisor.network import load_network
    from advisor.planner import IST, Advisor

    adv = Advisor(load_network(), online_places=False, online_routing=False)
    info = adv.bus_model.info()
    out = [check("advisor_uses_registry_champion",
                 info["available"] and info["active_source"] == "registry_champion" and info["version"] == champion_version,
                 info["detail"])]
    parity = info.get("parity") or {}
    out.append(check("prediction_parity_with_deployment", parity.get("ok") is True, parity.get("detail", "not run")))
    depart = datetime(2026, 11, 23, 17, 10, tzinfo=IST)  # a Monday evening peak
    lines, used_model, ok = [], 0, True
    for a, b in (("Lajpat Nagar", "Karol Bagh"), ("Chirag Delhi", "Nehru Place Terminal")):
        try:
            origin, destination = adv.search_places(a, online=False)[0], adv.search_places(b, online=False)[0]
            result = adv.plan(origin, destination, depart)
            journeys = result["journeys"]
            used_model += sum(j["uses_bus_model"] for j in journeys)
            top = journeys[0]
            lines.append(f"{a} -> {b}: {len(journeys)} options, top {' + '.join(top['modes'])} "
                         f"{top['duration_min']} min Rs {top['fare_inr']}")
        except Exception as exc:  # a planner failure fails the gate with the reason
            ok = False
            lines.append(f"{a} -> {b}: {type(exc).__name__}: {exc}")
    out.append(check("sample_delhi_plans", ok and used_model > 0,
                     "; ".join(lines) + f"; options using the bus model: {used_model}"))
    return out


def test_check(root: Path) -> dict:
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_advisor.py"]
    try:
        run = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=1200)
    except Exception as exc:
        return check("advisor_tests_pass", False, f"could not run pytest ({type(exc).__name__}: {exc})")
    tail = [line for line in run.stdout.splitlines() if line.strip()]
    return check("advisor_tests_pass", run.returncode == 0, tail[-1] if tail else (run.stderr.strip()[-300:] or "no output"))


def release_gate(checks: list[dict]) -> dict:
    return {"kind": "release", "passed": all(c["passed"] for c in checks), "checks": checks}


# ----- registration -------------------------------------------------------------------------------

def find_release(ledger: Ledger, fingerprint: str) -> dict | None:
    return next((r for r in ledger.versions if (r.get("release") or {}).get("fingerprint") == fingerprint), None)


def register_release(ledger: Ledger, registry_dir: Path, manifest: dict, gate: dict, *, expected_version: int,
                     code: dict | None = None, actor: str | None = None) -> dict:
    """Write the release as a new ledger version. Every step is audited; champion/previous do not move."""
    if not gate["passed"]:
        failed = ", ".join(c["name"] for c in gate["checks"] if not c["passed"])
        raise ValueError(f"The release gate failed ({failed}); nothing was registered.")
    existing = find_release(ledger, manifest["fingerprint"])
    if existing:
        return existing
    if ledger.next_version() != expected_version:
        raise ValueError(f"The next ledger version is v{ledger.next_version()}, not v{expected_version}; nothing was "
                         f"registered. Pass --expect-version {ledger.next_version()} to register it under that number.")
    champion = ledger.champion()
    version = ledger.next_version()
    model_bytes = (registry_dir.parent / champion["artifact"]["path"]).read_bytes()
    folder = registry_dir / f"v{version}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "model.joblib").write_bytes(model_bytes)
    artifact = {"path": f"registry/v{version}/model.joblib", "sha256": sha256(model_bytes).hexdigest(), "bytes": len(model_bytes)}
    if artifact["sha256"] != champion["artifact"]["sha256"]:
        raise ValueError("The copied model differs from the champion artifact; nothing was registered.")
    inherited = {key: champion[key] for key in (
        "training_window", "data", "algorithm", "hyperparameters", "features", "history_policy", "feature_schema_sha256",
        "runtime", "holdout", "holdout_metrics", "holdout_mae_by_segment", "data_validation") if key in champion}
    record = ledger.add_version({
        "status": "candidate", "change_type": "system_release",
        "reason": (f"Delhi multimodal advisor release: the journey planner, the pinned Delhi bus/metro/rail data snapshot, "
                   f"fares and cab settings, packaged with the v{champion['version']} bus model weights unchanged (same "
                   f"artifact sha256). Registered so the advisor's whole serving configuration is versioned; the champion "
                   f"alias stays on v{champion['version']}."),
        "trigger": {"type": "system_release", "fingerprint": manifest["fingerprint"]},
        "parent_version": champion["version"], "source": "advisor_release", **inherited,
        "code": code or {"git_head": None, "worktree_dirty": None}, "artifact": artifact, "quarantined": False,
        "gate": gate, "release": {**manifest, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }, actor=actor)
    ledger.set_status(record["version"], "approved", reason="Every release-gate check passed.", actor=actor)
    ledger.set_alias(RELEASE_ALIAS, record["version"], actor=actor,
                     reason=f"The Delhi advisor serves release v{record['version']} (bus model weights of v{champion['version']}).")
    return ledger.get(record["version"])
