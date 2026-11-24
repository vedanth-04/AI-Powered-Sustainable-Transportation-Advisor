"""Model version ledger with aliases and a hash-chained audit log.

The ledger is the project's source of truth for which model versions exist, why each
was created, what it was trained on, and which version serves. It is mirrored into the
MLflow Model Registry when MLflow is available, but it does not depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import getpass
from hashlib import sha256
import json
import os
from pathlib import Path

LEDGER_SCHEMA_VERSION = 1
GENESIS = "0" * 64
STATUSES = {"candidate", "approved", "rejected"}
RESERVED_ALIASES = {"champion", "previous"}  # these move only through promote() and rollback()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_actor() -> str:
    return os.environ.get("MLOPS_ACTOR") or getpass.getuser()


def _canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()


@dataclass
class Ledger:
    path: Path
    model_name: str = "BusTravelTimePredictor"
    versions: list[dict] = field(default_factory=list)
    aliases: dict[str, int] = field(default_factory=dict)

    @property
    def audit_path(self) -> Path:
        return self.path.with_name("audit_log.jsonl")

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != LEDGER_SCHEMA_VERSION:
            raise ValueError("Unsupported ledger schema.")
        return cls(path, data["model_name"], data["versions"], {k: int(v) for k, v in data["aliases"].items()})

    @classmethod
    def create(cls, path: Path, model_name: str = "BusTravelTimePredictor") -> "Ledger":
        if path.exists():
            raise FileExistsError(f"A ledger already exists at {path}.")
        path.parent.mkdir(parents=True, exist_ok=True)
        ledger = cls(path, model_name)
        ledger.save()
        return ledger

    def save(self) -> None:
        data = {"schema_version": LEDGER_SCHEMA_VERSION, "model_name": self.model_name,
                "aliases": self.aliases, "versions": self.versions}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    # ----- queries -------------------------------------------------------------------------
    def get(self, version: int) -> dict:
        for record in self.versions:
            if record["version"] == version:
                return record
        raise KeyError(f"Version {version} is not in the ledger.")

    def next_version(self) -> int:
        return max((record["version"] for record in self.versions), default=0) + 1

    def champion(self) -> dict | None:
        return self.get(self.aliases["champion"]) if "champion" in self.aliases else None

    # ----- changes (every change is audited) -------------------------------------------------
    def add_version(self, record: dict, *, actor: str | None = None) -> dict:
        if record.get("status") not in STATUSES:
            raise ValueError(f"Status must be one of {sorted(STATUSES)}.")
        record = {"version": self.next_version(), "model_name": self.model_name, "created_at": now_utc(), **record}
        self.versions.append(record)
        self.save()
        self.audit("register_version", actor=actor, version=record["version"], status=record["status"],
                   reason=record.get("reason"))
        return record

    def set_status(self, version: int, status: str, *, reason: str, actor: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"Status must be one of {sorted(STATUSES)}.")
        record = self.get(version)
        old = record["status"]
        record["status"] = status
        record.setdefault("status_history", []).append({"at": now_utc(), "from": old, "to": status, "reason": reason})
        self.save()
        self.audit("set_status", actor=actor, version=version, before=old, after=status, reason=reason)

    def promote(self, version: int, *, reason: str, actor: str | None = None) -> None:
        """Make an approved version the champion and keep the old champion as `previous`."""
        if self.get(version)["status"] != "approved":
            raise ValueError("Only an approved version can become the champion.")
        old = self.aliases.get("champion")
        if old == version:
            return
        if old is not None:
            self.aliases["previous"] = old
        self.aliases["champion"] = version
        self.save()
        self.audit("promote", actor=actor, version=version, before=old, after=version, reason=reason)

    def rollback(self, *, reason: str, actor: str | None = None) -> int:
        """Swap champion and previous: one step back to the last known-good version."""
        if "previous" not in self.aliases:
            raise ValueError("There is no previous version to roll back to.")
        old, target = self.aliases["champion"], self.aliases["previous"]
        self.aliases["champion"], self.aliases["previous"] = target, old
        self.save()
        self.audit("rollback", actor=actor, version=target, before=old, after=target, reason=reason)
        return target

    def set_alias(self, alias: str, version: int, *, reason: str, actor: str | None = None) -> None:
        """Point a named alias (for example `advisor`) at a version. champion/previous are not set here."""
        if alias in RESERVED_ALIASES:
            raise ValueError(f"The {alias} alias moves only through promote() and rollback().")
        self.get(version)
        old = self.aliases.get(alias)
        if old == version:
            return
        self.aliases[alias] = version
        self.save()
        self.audit("set_alias", actor=actor, alias=alias, version=version, before=old, after=version, reason=reason)

    def audit(self, action: str, *, actor: str | None = None, **details) -> dict:
        entries = read_audit(self.audit_path)
        previous_hash = entries[-1]["entry_sha256"] if entries else GENESIS
        entry = {"sequence": len(entries) + 1, "at": now_utc(), "actor": actor or default_actor(),
                 "action": action, "model_name": self.model_name, **details, "previous_sha256": previous_hash}
        entry["entry_sha256"] = sha256(_canonical(entry)).hexdigest()
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, default=str) + "\n")
        return entry


def read_audit(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_audit_chain(path: Path) -> dict:
    """Recompute every entry hash; editing or deleting a past entry breaks the chain."""
    previous = GENESIS
    entries = read_audit(path)
    for entry in entries:
        body = {key: value for key, value in entry.items() if key != "entry_sha256"}
        if entry.get("previous_sha256") != previous or sha256(_canonical(body)).hexdigest() != entry.get("entry_sha256"):
            return {"valid": False, "entries": len(entries), "broken_at_sequence": entry.get("sequence")}
        previous = entry["entry_sha256"]
    return {"valid": True, "entries": len(entries), "head_sha256": previous}


def diff_versions(old: dict, new: dict) -> list[dict]:
    """What changed between two versions, in the terms that justify a new version number."""
    checks = [
        ("Training data window", lambda r: ", ".join(r.get("training_window", {}).get("dates_ist", []))),
        ("Training rows", lambda r: r.get("training_window", {}).get("rows")),
        ("Training rows sha256", lambda r: r.get("training_window", {}).get("rows_sha256")),
        ("Source file sha256", lambda r: r.get("data", {}).get("input_sha256")),
        ("Algorithm", lambda r: r.get("algorithm")),
        ("Hyperparameters", lambda r: json.dumps(r.get("hyperparameters"), sort_keys=True)),
        ("Feature schema sha256", lambda r: r.get("feature_schema_sha256")),
        ("History policy", lambda r: r.get("history_policy")),
        ("Code commit", lambda r: r.get("code", {}).get("git_head")),
        ("scikit-learn", lambda r: r.get("runtime", {}).get("scikit-learn")),
        ("Artifact sha256", lambda r: r.get("artifact", {}).get("sha256")),
        ("System release fingerprint", lambda r: (r.get("release") or {}).get("fingerprint")),
    ]
    return [{"field": name, "old": get(old), "new": get(new), "changed": get(old) != get(new)} for name, get in checks]
