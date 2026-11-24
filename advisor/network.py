"""Load the prebuilt network (data/processed/advisor) into router-friendly arrays."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from advisor.geo import haversine_km_vec
from advisor.ingest import BUS, METRO, RAIL, MODE_NAMES, OUT_DIR, load_json

WEEKDAY_BITS = 0b0011111


@dataclass
class Network:
    lat: np.ndarray
    lon: np.ndarray
    mode: np.ndarray
    names: list[str]
    src: list[str]
    patterns: list[dict]
    pat_stops: list[np.ndarray]
    pat_km: list[np.ndarray]
    arr: list[np.ndarray]          # trips x stops
    dep_t: list[np.ndarray]        # stops x trips (contiguous columns for searchsorted)
    fare: list[np.ndarray | None]  # stops x stops official bus stage fares (0 = unknown)
    fp_off: np.ndarray
    fp_to: np.ndarray
    fp_sec: np.ndarray
    stop_pat_off: np.ndarray
    stop_pat: np.ndarray           # (pattern, position) rows
    meta: dict
    config: dict = field(default_factory=dict)
    data_dir: Path | None = None

    @property
    def n_stops(self) -> int:
        return len(self.lat)

    def pattern_mode(self, p: int) -> int:
        return self.patterns[p]["mode"]

    def active_patterns(self, dow: int) -> tuple[np.ndarray, list[str]]:
        """Boolean mask of patterns running on weekday `dow` (0=Mon) and any caveats."""
        bit = 1 << dow
        days = np.array([p["days"] for p in self.patterns])
        modes = np.array([p["mode"] for p in self.patterns])
        active = (days & bit) > 0
        notes = []
        metro_today = int((active & (modes == METRO)).sum())
        if dow >= 5 and metro_today < 10:
            active |= (modes == METRO) & ((days & WEEKDAY_BITS) > 0)
            notes.append("The DMRC feed has almost no weekend trips, so the weekday metro timetable is used; "
                         "weekend frequencies are usually lower.")
        return active, notes

    def nearby(self, lat: float, lon: float, radius_m: float, modes: set[int] | None = None) -> list[tuple[int, float]]:
        d = haversine_km_vec(lat, lon, self.lat, self.lon) * 1000.0
        idx = np.flatnonzero(d <= radius_m)
        if modes is not None:
            idx = idx[np.isin(self.mode[idx], list(modes))]
        return sorted(((int(i), float(d[i])) for i in idx), key=lambda x: x[1])


def load_network(out_dir: Path = OUT_DIR) -> Network:
    npz_path, meta_path = out_dir / "network.npz", out_dir / "network_meta.json"
    if not npz_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"{npz_path} not found; run python -m scripts.advisor_build_network")
    z = np.load(npz_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    pats = meta["patterns"]
    so, ps, pk = z["pat_stop_off"], z["pat_stops"], z["pat_km"]
    to, pa, pd_ = z["pat_time_off"], z["pat_arr"], z["pat_dep"]
    fo, pf = z["pat_fare_off"], z["pat_fare"]
    stops_l, km_l, arr_l, dep_l, fare_l = [], [], [], [], []
    rows = []
    for p, info in enumerate(pats):
        seq = ps[so[p]:so[p + 1]]
        n = len(seq)
        trips = info["n_trips"]
        stops_l.append(seq)
        km_l.append(pk[so[p]:so[p + 1]].astype(float))
        arr_l.append(pa[to[p]:to[p + 1]].reshape(trips, n))
        dep_l.append(np.ascontiguousarray(pd_[to[p]:to[p + 1]].reshape(trips, n).T))
        fare_l.append(pf[fo[p]:fo[p + 1]].reshape(n, n) if fo[p + 1] > fo[p] else None)
        rows.extend((int(s), p, i) for i, s in enumerate(seq))
    rows.sort()
    n_stops = len(z["stop_lat"])
    stop_pat_off = np.zeros(n_stops + 1, dtype=np.int64)
    for s, _, _ in rows:
        stop_pat_off[s + 1] += 1
    stop_pat_off = np.cumsum(stop_pat_off)
    stop_pat = np.array([(p, i) for _, p, i in rows], dtype=np.int32).reshape(-1, 2)
    return Network(
        lat=z["stop_lat"], lon=z["stop_lon"], mode=z["stop_mode"],
        names=[s["name"] for s in meta["stops"]], src=[s["src"] for s in meta["stops"]],
        patterns=pats, pat_stops=stops_l, pat_km=km_l, arr=arr_l, dep_t=dep_l, fare=fare_l,
        fp_off=z["fp_off"], fp_to=z["fp_to"], fp_sec=z["fp_sec"],
        stop_pat_off=stop_pat_off, stop_pat=stop_pat, meta=meta, config=load_json("advisor_config.json"), data_dir=out_dir,
    )


__all__ = ["Network", "load_network", "BUS", "METRO", "RAIL", "MODE_NAMES"]
