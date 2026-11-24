"""Cab legs: road distance and time, pickup wait, indicative meter fare and CO2.

Road routing uses OSRM (OpenStreetMap road network) when it can be reached: one table request per side of a
trip gives distances and free-flow durations to every candidate station, and a route request draws the road
path for the cab legs that end up in the answer. OSRM assumes free-flowing roads, so durations are multiplied
by a time-of-day Delhi traffic factor; a pickup wait is added. Without routing the distance is the straight
line times a detour factor at an assumed free-flow speed. Every leg says which method produced it.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass

from advisor.geo import haversine_km


@dataclass
class CabEstimate:
    km: float
    drive_sec: int          # with the traffic factor applied
    free_flow_sec: int
    pickup_sec: int
    traffic_factor: float
    method: str             # "osrm" | "rule"

    @property
    def total_sec(self) -> int:
        return self.pickup_sec + self.drive_sec


class CabRouter:
    def __init__(self, config: dict, online: bool = True):
        self.cfg = config["cab"]
        self.online = online and self.cfg["routing"].get("provider") == "osrm"
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._offline_until = 0.0
        self.last_error: str | None = None

    # ------------------------------------------------------------ time of day
    def period(self, clock_sec: int) -> dict:
        hour = (clock_sec // 3600) % 24
        for p in self.cfg["traffic_factor"]:
            if p["from_h"] <= hour < p["to_h"]:
                return p
        return self.cfg["traffic_factor"][-1]

    def is_night(self, clock_sec: int) -> bool:
        n = self.cfg["night_hours"]
        hour = (clock_sec // 3600) % 24
        return hour >= n["from_h"] or hour < n["to_h"]

    # ------------------------------------------------------------ OSRM
    @property
    def status(self) -> dict:
        if not self.online:
            return {"state": "off", "detail": "road routing disabled; straight-line rule used"}
        if time.time() < self._offline_until:
            return {"state": "unreachable", "detail": self.last_error}
        return {"state": "ready", "detail": f"OSRM at {self.cfg['routing']['url']}"}

    def _get(self, path: str):
        if not self.online or time.time() < self._offline_until:
            return None
        url = self.cfg["routing"]["url"].rstrip("/") + path
        with self._lock:
            if url in self._cache:
                self._cache.move_to_end(url)
                return self._cache[url]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.cfg["routing"].get("user_agent", "DelhiCommuteAdvisor/1.0")})
            with urllib.request.urlopen(req, timeout=self.cfg["routing"].get("timeout_s", 4)) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("code") != "Ok":
                raise ValueError(body.get("message") or body.get("code"))
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._offline_until = time.time() + self.cfg["routing"].get("retry_after_failure_s", 120)
            return None
        with self._lock:
            self._cache[url] = body
            while len(self._cache) > 500:
                self._cache.popitem(last=False)
        return body

    @staticmethod
    def _coords(points) -> str:
        return ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)

    def _table(self, sources: list, destinations: list):
        """(distance km matrix, duration sec matrix) from OSRM, or None."""
        pts = sources + destinations
        src = ";".join(str(i) for i in range(len(sources)))
        dst = ";".join(str(len(sources) + i) for i in range(len(destinations)))
        body = self._get(f"/table/v1/driving/{self._coords(pts)}?sources={src}&destinations={dst}&annotations=duration,distance")
        if not body or not body.get("distances") or not body.get("durations"):
            return None
        return body["distances"], body["durations"]

    def route_path(self, a: tuple, b: tuple) -> list | None:
        body = self._get(f"/route/v1/driving/{self._coords([a, b])}?overview=simplified&geometries=geojson")
        try:
            return [[lat, lon] for lon, lat in body["routes"][0]["geometry"]["coordinates"]]
        except (TypeError, KeyError, IndexError):
            return None

    # ------------------------------------------------------------ estimates
    def _make(self, km: float, free_sec: float, clock_sec: int, method: str) -> CabEstimate:
        p = self.period(clock_sec)
        return CabEstimate(km=round(km, 2), drive_sec=int(round(free_sec * p["factor"])), free_flow_sec=int(round(free_sec)),
                           pickup_sec=int(p["pickup_wait_min"] * 60), traffic_factor=p["factor"], method=method)

    def _rule(self, a: tuple, b: tuple, clock_sec: int) -> CabEstimate:
        f = self.cfg["fallback"]
        km = haversine_km(a[0], a[1], b[0], b[1]) * f["road_detour_factor"]
        return self._make(km, km / f["free_flow_speed_kmh"] * 3600, clock_sec, "rule")

    def one_to_many(self, origin: tuple, targets: list[tuple], clock_sec: int) -> list[CabEstimate]:
        table = self._table([origin], targets) if targets else None
        out = []
        for i, t in enumerate(targets):
            if table and table[0][0][i] is not None and table[1][0][i] is not None:
                out.append(self._make(table[0][0][i] / 1000.0, table[1][0][i], clock_sec, "osrm"))
            else:
                out.append(self._rule(origin, t, clock_sec))
        return out

    def many_to_one(self, sources: list[tuple], dest: tuple, clock_sec: int) -> list[CabEstimate]:
        table = self._table(sources, [dest]) if sources else None
        out = []
        for i, s in enumerate(sources):
            if table and table[0][i][0] is not None and table[1][i][0] is not None:
                out.append(self._make(table[0][i][0] / 1000.0, table[1][i][0], clock_sec, "osrm"))
            else:
                out.append(self._rule(s, dest, clock_sec))
        return out

    # ------------------------------------------------------------ money and CO2
    def fare(self, km: float, cab_type: str, start_clock_sec: int) -> tuple[float, str]:
        t = self.cfg["types"][cab_type]
        extra_km = max(0.0, km - t["base_km"])
        price = t["base_inr"] + extra_km * t["per_km_inr"]
        basis = (f"{t['label']} meter fare: ₹{t['base_inr']} for the first {t['base_km']:g} km + ₹{t['per_km_inr']}/km "
                 f"x {extra_km:.1f} km")
        if self.is_night(start_clock_sec):
            price *= 1 + t["night_surcharge"]
            basis += f" + {int(t['night_surcharge'] * 100)}% night charge"
        return float(round(price)), basis + " (indicative)"

    def co2(self, km: float, cab_type: str) -> float:
        t = self.cfg["types"][cab_type]
        return km * t["kg_co2_per_vkm"] / max(1.0, t["occupancy"])
