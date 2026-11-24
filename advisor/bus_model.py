"""Bus travel-time model, used the governed way.

Where it is used
    Only on the segment the model is approved for: Outer Ring Road eastbound, Chirag Delhi -> Nehru Place
    (ORR_CHIRAG_TO_NEHRU_PLACE_EB). A bus leg that rides that stretch gets the model's time for it; every
    other part of every journey uses timetables (metro, rail, rest of the bus network) or walking rules.

Which model
    The first source in config["bus_model"]["sources"] that passes its checks:
      registry_champion  Phase 3 registry 'champion' alias -> outputs/phase3/serving/v<N>. Requires a valid
                         hash-chained audit log, status 'approved', a passed promotion gate and an artifact
                         sha256 equal to the registry record.
      deployed_service   the running Docker API (POST /predict/bus) on localhost.
      approved_bundle    the Phase 2 approved serving bundle (outputs/phase2_serving).
    Bundles are loaded read-only with src.api.bundle.load_bundle (scikit-learn version, feature schema
    and artifact checksum checks). Nothing under outputs/ is written.

How
    The request is built exactly like the serving API does (src.api.main.predict_bus): segment, direction,
    segment length, the approved route id and the entry time, through engineer_features(...,
    use_observed_history=False) - the cold_start_v1 policy. The entry time is when the bus reaches the
    segment. A parity check reproduces the deployment record's expected minutes for v1.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from advisor.geo import haversine_km
from advisor.ingest import ROOT

DEMO_ENTRY = "2019-07-08T17:10:00+05:30"  # the request recorded in deploy/model-v1.json


class _BundleSource:
    def __init__(self, name: str, bundle, detail: str, typical_error: float | None):
        self.name, self.bundle, self.detail, self.typical_error = name, bundle, detail, typical_error
        self.version = int(bundle.manifest.model_version)
        self.route_id = bundle.manifest.route_id

    def predict(self, entry: datetime) -> float:
        from src.features.build_features import engineer_features

        m, seg = self.bundle.manifest, self.bundle.segment
        frame = pd.DataFrame([{"segment_id": seg.segment_id, "direction": seg.direction,
                               "segment_length_km": seg.length_km, "route_id": m.route_id, "t_entry": entry.timestamp()}])
        features = engineer_features(frame, use_observed_history=False)[m.features]
        value = float(np.asarray(self.bundle.model.predict(features), dtype=float)[0])
        if not np.isfinite(value) or value <= 0:
            raise ValueError("invalid model output")
        return value


class _ServiceSource:
    def __init__(self, url: str, segment_id: str, route_id: str, health: dict):
        self.name, self.url, self.segment_id, self.route_id = "deployed_service", url.rstrip("/"), segment_id, route_id
        self.version = int(health.get("model_version", 0))
        self.detail = f"Docker API at {self.url} (model v{self.version}, {health.get('history_policy')})"
        self.typical_error = None

    def predict(self, entry: datetime) -> float:
        body = json.dumps({"segment_id": self.segment_id, "route_id": self.route_id, "entry_at": entry.isoformat()}).encode()
        req = urllib.request.Request(self.url + "/predict/bus", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            value = float(json.loads(resp.read())["duration_minutes"])
        if not np.isfinite(value) or value <= 0:
            raise ValueError("invalid service output")
        return value


class BusModel:
    def __init__(self, config: dict, root: Path = ROOT):
        self.cfg = config["bus_model"]
        self.root = root
        self.sources_status: list[dict] = []
        self._sources: list = []
        self._cache: dict = {}
        self.active = None
        self.segment = None
        self.parity: dict | None = None
        if not self.cfg.get("enabled"):
            self.sources_status.append({"source": "all", "ok": False, "detail": "disabled in advisor_config.json"})
            return
        try:
            from src.features.segment_config import get_segment

            self.segment = get_segment(self.cfg["segment_id"])
        except Exception as exc:
            self.sources_status.append({"source": "all", "ok": False, "detail": f"project code not importable: {exc}"})
            return
        for name in self.cfg.get("sources", []):
            try:
                src = getattr(self, f"_open_{name}")()
                self._sources.append(src)
                self.sources_status.append({"source": name, "ok": True, "version": src.version, "detail": src.detail})
            except Exception as exc:
                self.sources_status.append({"source": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        self.active = self._sources[0] if self._sources else None
        self.parity = self._parity_check()

    # ------------------------------------------------------------ sources
    def _open_registry_champion(self):
        from src.api.bundle import load_bundle
        from src.versioning.ledger import verify_audit_chain

        reg = self.root / self.cfg["registry_dir"]
        ledger = json.loads((reg / "model_versions.json").read_text(encoding="utf-8"))
        chain = verify_audit_chain(reg / "audit_log.jsonl")
        if not chain["valid"]:
            raise ValueError(f"audit chain broken at entry {chain.get('broken_at_sequence')}")
        version = ledger["aliases"]["champion"]
        record = next(r for r in ledger["versions"] if r["version"] == version)
        if record["status"] != "approved":
            raise ValueError(f"champion v{version} is {record['status']}")
        if record.get("gate") is not None and not record["gate"].get("passed"):
            raise ValueError(f"champion v{version} did not pass the promotion gate")
        bundle_dir = self.root / self.cfg["serving_dir"] / f"v{version}"
        if not bundle_dir.exists() and version == 1:
            bundle_dir = self.root / self.cfg["bundle_dir"]
        bundle = load_bundle(bundle_dir)
        if bundle.manifest.model_sha256 != record["artifact"]["sha256"] or bundle.manifest.model_version != version:
            raise ValueError("serving bundle does not match the registry record")
        if bundle.manifest.segment_id != self.cfg["segment_id"]:
            raise ValueError("bundle covers a different segment")
        mae = (record.get("holdout_mae_by_segment") or {}).get(self.cfg["segment_id"])
        gate = "gate passed" if record.get("gate") else "approved release"
        return _BundleSource("registry_champion", bundle,
                             f"Phase 3 registry champion v{version} ({gate}; audit chain valid, {chain['entries']} entries; "
                             f"artifact sha256 {record['artifact']['sha256'][:12]}...)", mae)

    def _open_deployed_service(self):
        url = self.cfg["service_url"]
        from urllib.parse import urlsplit

        if urlsplit(url).hostname not in ("127.0.0.1", "localhost"):
            raise ValueError("only a service on this machine is allowed")
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=1.0) as resp:
            health = json.loads(resp.read())
        if health.get("status") != "ready":
            raise ValueError(f"service not ready: {health}")
        return _ServiceSource(url, self.cfg["segment_id"], "90", health)

    def _open_approved_bundle(self):
        from src.api.bundle import load_bundle

        bundle = load_bundle(self.root / self.cfg["bundle_dir"])
        if bundle.manifest.segment_id != self.cfg["segment_id"]:
            raise ValueError("bundle covers a different segment")
        return _BundleSource("approved_bundle", bundle,
                             f"Phase 2 approved bundle v{bundle.manifest.model_version} ({self.cfg['bundle_dir']})", None)

    def _parity_check(self) -> dict | None:
        """Reproduce the deployment record's expected v1 prediction through this adapter."""
        record_path = self.root / self.cfg.get("deployment_record", "")
        v1 = next((s for s in self._sources if isinstance(s, _BundleSource) and s.version == 1), None)
        if v1 is None:
            try:
                v1 = self._open_approved_bundle()
            except Exception as exc:
                return {"ok": None, "detail": f"v1 bundle not loadable here ({type(exc).__name__}); parity not checked"}
        if not record_path.is_file():
            return {"ok": None, "detail": "deployment record not found; parity not checked"}
        expected = float(json.loads(record_path.read_text(encoding="utf-8"))["expected_minutes"])
        got = v1.predict(datetime.fromisoformat(DEMO_ENTRY))
        ok = abs(got - expected) < 1e-6
        return {"ok": ok, "expected_minutes": expected, "adapter_minutes": got,
                "detail": f"v1 at {DEMO_ENTRY}: adapter {got:.6f} min vs deployment record {expected:.6f} min"}

    # ------------------------------------------------------------ public
    @property
    def available(self) -> bool:
        return self.active is not None

    @property
    def version(self):
        return self.active.version if self.active else None

    @property
    def reason(self) -> str:
        if self.active:
            return f"Using {self.active.detail}. Applied only to {self.cfg['segment_id']}."
        fails = "; ".join(f"{s['source']}: {s['detail']}" for s in self.sources_status)
        return f"No bus model source passed its checks ({fails}). Timetable times are used everywhere."

    def info(self) -> dict:
        return {"available": self.available, "active_source": self.active.name if self.active else None,
                "version": self.version, "segment": self.cfg["segment_id"],
                "typical_error_min": round(self.active.typical_error, 2) if self.active and self.active.typical_error else None,
                "sources": self.sources_status, "parity": self.parity, "detail": self.reason}

    def predict_minutes(self, entry: datetime) -> tuple[float, str, int]:
        """(minutes for the full gate-to-gate segment, source name, model version)."""
        key = entry.replace(second=0, microsecond=0)
        if key in self._cache:
            return self._cache[key]
        last = None
        for src in [self.active] + [s for s in self._sources if s is not self.active]:
            if src is None:
                continue
            try:
                result = (src.predict(key), src.name, src.version)
                self._cache[key] = result
                return result
            except Exception as exc:
                last = exc
        raise RuntimeError(f"no model source could predict ({last})")

    def corridor_run(self, lats: list[float], lons: list[float]) -> tuple[int, int] | None:
        """Positions (i, j) of the leg's stops that ride the corridor eastbound between the gates, else None."""
        c = self.cfg["corridor"]
        n = len(lats)
        i = 0
        while i < n:
            if c["lat_min"] <= lats[i] <= c["lat_max"] and c["start_lon_min"] <= lons[i] <= c["start_lon_max"]:
                j = i
                while (j + 1 < n and c["lat_min"] <= lats[j + 1] <= c["lat_max"]
                       and lons[j] < lons[j + 1] <= c["end_lon_max"]):
                    j += 1
                if lons[j] >= c["end_lon_min"] and j > i:
                    return i, j
                i = j + 1
            else:
                i += 1
        return None

    def segment_minutes(self, entry: datetime, lat1, lon1, lat2, lon2) -> tuple[float, float, str, int]:
        """Model minutes for the covered part of the segment, scaled by its share of the gate-to-gate length."""
        span = haversine_km(lat1, lon1, lat2, lon2)
        share = min(1.0, span / self.segment.length_km)
        minutes, source, version = self.predict_minutes(entry)
        return minutes * share, share, source, version

    def day_profile(self, day: datetime, start_h: int = 5, end_h: int = 23, step_min: int = 30) -> list[dict]:
        base = day.replace(hour=0, minute=0, second=0, microsecond=0)
        out = []
        for m in range(start_h * 60, end_h * 60 + 1, step_min):
            t = base + timedelta(minutes=m)
            try:
                minutes, _, _ = self.predict_minutes(t)
                out.append({"time": t.strftime("%H:%M"), "minutes": round(minutes, 2)})
            except Exception:
                out.append({"time": t.strftime("%H:%M"), "minutes": None})
        return out
