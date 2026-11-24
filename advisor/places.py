"""Place names for Delhi: offline localities (municipal wards) + the NCT boundary, and an online
OpenStreetMap geocoder (Photon / Nominatim) used through the backend with caching and rate limits.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from pathlib import Path

import numpy as np

from advisor.geo import haversine_km

SKIP_WARD = re.compile(r"CHARGE \d+$")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(text).lower())).strip()


def pretty_ward(name: str) -> str:
    text = re.sub(r"\s+", " ", name.replace("-", " - ")).strip().title()
    text = re.sub(r"\s-\s(I+)$", lambda m: f" {m.group(1).upper()}", text)
    fixes = {"Ext.": "Extension", "Extention": "Extension", "Extn": "Extension", "Ii": "II", "R. K.": "R.K.",
             "G.T.B.": "GTB", "I.P": "I.P."}
    for a, b in fixes.items():
        text = re.sub(rf"\b{re.escape(a)}(?=\s|$)", b, text)
    return text.replace(" - ", "-")


# ---------------------------------------------------------------- geometry

def ring_area_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    """Signed area and centroid of a lon/lat ring (planar, fine at ward scale)."""
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a *= 0.5
    if abs(a) < 1e-12:
        xs, ys = zip(*ring)
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    return a, cx / (6 * a), cy / (6 * a)


def point_in_ring(lon: float, lat: float, ring) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def distance_to_ring_km(lon: float, lat: float, ring) -> float:
    """Approximate distance from a point to a polygon outline (km)."""
    kx, ky = 111.32 * np.cos(np.radians(lat)), 110.57
    pts = np.asarray(ring, dtype=float)
    ax, ay = (pts[:, 0] - lon) * kx, (pts[:, 1] - lat) * ky
    bx, by = np.roll(ax, -1), np.roll(ay, -1)
    dx, dy = bx - ax, by - ay
    t = np.clip(-(ax * dx + ay * dy) / np.maximum(dx * dx + dy * dy, 1e-12), 0, 1)
    px, py = ax + t * dx, ay + t * dy
    return float(np.sqrt(px * px + py * py).min())


def build_places(raw_dir: Path, out_dir: Path) -> dict:
    """data/raw/transit/places/*.geojson -> data/processed/advisor/places.json."""
    d = raw_dir / "places"
    boundary = json.loads((d / "Delhi_Boundary.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"][0]
    wards = json.loads((d / "Delhi_Wards.geojson").read_text(encoding="utf-8"))["features"]
    localities = []
    for f in wards:
        name = f["properties"].get("Ward_Name")
        if not name:
            continue
        ring = f["geometry"]["coordinates"][0]
        _, lon, lat = ring_area_centroid(ring[:-1] if ring[0] == ring[-1] else ring)
        if not point_in_ring(lon, lat, ring):  # concave ward: use the vertex mean instead
            lon = float(np.mean([p[0] for p in ring])); lat = float(np.mean([p[1] for p in ring]))
        step = max(1, len(ring) // 60)
        simple = [[round(p[0], 5), round(p[1], 5)] for p in ring[::step]]
        label = pretty_ward(name)
        if name.startswith("NDMC CHARGE"):
            label = "New Delhi (NDMC area)"
        elif name.startswith("DELHI CANTT CHARGE"):
            label = "Delhi Cantonment"
        localities.append({"name": label, "ward": name.title(), "lat": round(lat, 6), "lon": round(lon, 6),
                           "searchable": not SKIP_WARD.search(name), "ring": simple})
    out = {"boundary": [[round(p[0], 6), round(p[1], 6)] for p in boundary], "localities": localities}
    (out_dir / "places.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    return {"localities": sum(1 for l in localities if l["searchable"]), "boundary_points": len(boundary)}


# ---------------------------------------------------------------- gazetteer

class Gazetteer:
    """Offline Delhi place names + boundary check + optional online OSM geocoding."""

    def __init__(self, places_path: Path, config: dict, stops: list[dict] | None = None, online: bool | None = None):
        data = json.loads(places_path.read_text(encoding="utf-8"))
        self.boundary = data["boundary"]
        self.localities = data["localities"]
        self.cfg = config.get("geocoder", {})
        self.tolerance = config["service_area"].get("boundary_tolerance_km", 1.0)
        self.online_enabled = self.cfg.get("online", False) if online is None else online
        self.stops = stops or []
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._offline_until = 0.0
        self._last_nominatim = 0.0
        self.last_error: str | None = None
        for loc in self.localities:
            loc["_key"] = norm(loc["name"])
        self._anchor_localities()

    def _anchor_localities(self) -> None:
        """A ward's geometric centre can be far from where people mean by its name. When a metro station,
        rail halt or bus stop carries the locality's name and lies inside or near the ward, use it as the
        locality's point (e.g. 'Karol Bagh' -> Karol Bagh metro station area)."""
        order = {"metro": 0, "rail": 1, "bus": 2}
        by_key: dict[str, list] = {}
        for st in self.stops:
            key = norm(re.sub(r"\([A-Z]+\)$", "", st["name"]))
            by_key.setdefault(key, []).append(st)
        for loc in self.localities:
            cands = [st for st in by_key.get(loc["_key"], [])
                     if haversine_km(loc["lat"], loc["lon"], st["lat"], st["lon"]) <= 2.5]
            if not cands:
                continue
            best = min(cands, key=lambda st: (order.get(st["mode"], 3), haversine_km(loc["lat"], loc["lon"], st["lat"], st["lon"])))
            loc["anchor"] = {"name": best["name"], "mode": best["mode"]}
            loc["lat"], loc["lon"] = best["lat"], best["lon"]

    # -- boundary
    def inside_delhi(self, lat: float, lon: float) -> bool:
        if point_in_ring(lon, lat, self.boundary):
            return True
        return distance_to_ring_km(lon, lat, self.boundary) <= self.tolerance

    def locality_at(self, lat: float, lon: float) -> str | None:
        for loc in self.localities:
            if point_in_ring(lon, lat, loc["ring"]):
                return loc["name"]
        return None

    # -- online
    @property
    def online_status(self) -> dict:
        if not self.online_enabled:
            return {"enabled": False, "state": "off", "detail": "online geocoding disabled in advisor_config.json"}
        if time.time() < self._offline_until:
            return {"enabled": True, "state": "unreachable", "detail": self.last_error}
        return {"enabled": True, "state": "ready", "detail": "OpenStreetMap via Photon/Nominatim"}

    def _get_json(self, url: str, params: dict, nominatim: bool = False):
        if not self.online_enabled or time.time() < self._offline_until:
            return None
        full = url + "?" + urllib.parse.urlencode(params)
        with self._lock:
            if full in self._cache:
                self._cache.move_to_end(full)
                return self._cache[full]
            if nominatim:  # usage policy: at most one request per second
                wait = 1.0 - (time.time() - self._last_nominatim)
                if wait > 0:
                    time.sleep(wait)
                self._last_nominatim = time.time()
        try:
            req = urllib.request.Request(full, headers={"User-Agent": self.cfg.get("user_agent", "DelhiCommuteAdvisor/1.0"),
                                                        "Accept-Language": "en"})
            with urllib.request.urlopen(req, timeout=self.cfg.get("timeout_s", 3.5)) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # network down, proxy, rate limit ...
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._offline_until = time.time() + self.cfg.get("retry_after_failure_s", 60)
            return None
        with self._lock:
            self._cache[full] = body
            while len(self._cache) > 2000:
                self._cache.popitem(last=False)
        return body

    @staticmethod
    def _photon_label(p: dict) -> tuple[str, str]:
        name = p.get("name") or " ".join(x for x in (p.get("housenumber"), p.get("street")) if x) or p.get("district") or ""
        parts = []
        for key in ("street", "locality", "district", "city"):
            v = p.get(key)
            if v and v != name and v not in parts:
                parts.append(v)
        return name, ", ".join(parts[:3])

    def search_online(self, query: str, limit: int = 8) -> list[dict]:
        body = self._get_json(self.cfg["search_url"], {"q": query, "limit": limit + 4, "lang": "en",
                                                       "bbox": "76.83,28.40,77.35,28.89", "lat": 28.6139, "lon": 77.2090})
        out = []
        for f in (body or {}).get("features", []):
            lon, lat = f["geometry"]["coordinates"][:2]
            if not self.inside_delhi(lat, lon):
                continue
            name, detail = self._photon_label(f.get("properties", {}))
            if not name:
                continue
            kind = (f["properties"].get("osm_value") or f["properties"].get("type") or "place").replace("_", " ")
            out.append({"id": f"osm:{f['properties'].get('osm_type', '')}{f['properties'].get('osm_id', '')}",
                        "name": name, "detail": detail, "mode": "place", "kind": kind.title(),
                        "lat": round(lat, 6), "lon": round(lon, 6), "source": "OpenStreetMap"})
        return out[:limit]

    def reverse(self, lat: float, lon: float, online: bool = True) -> dict:
        locality = self.locality_at(lat, lon)
        nearest = None
        if self.stops:
            from advisor.geo import haversine_km_vec

            if not hasattr(self, "_stop_ll"):
                self._stop_ll = (np.array([s["lat"] for s in self.stops]), np.array([s["lon"] for s in self.stops]))
            d = haversine_km_vec(lat, lon, *self._stop_ll)
            i = int(np.argmin(d))
            nearest = {"name": self.stops[i]["name"], "mode": self.stops[i]["mode"], "distance_m": round(float(d[i]) * 1000)}
        name, detail, source = None, None, "offline"
        body = self._get_json(self.cfg["reverse_url"], {"lat": lat, "lon": lon, "lang": "en", "limit": 1}) if online else None
        feats = (body or {}).get("features") or []
        if feats:
            name, detail = self._photon_label(feats[0].get("properties", {}))
            source = "OpenStreetMap"
        elif online and self.online_enabled and self.cfg.get("fallback_reverse_url") and time.time() >= self._offline_until:
            nb = self._get_json(self.cfg["fallback_reverse_url"], {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 17,
                                                                  "addressdetails": 1}, nominatim=True)
            if nb and nb.get("display_name"):
                addr = nb.get("address", {})
                name = nb.get("name") or addr.get("road") or addr.get("suburb") or nb["display_name"].split(",")[0]
                detail = ", ".join(x for x in (addr.get("suburb"), addr.get("city_district")) if x)
                source = "OpenStreetMap"
        if not name:
            if nearest and nearest["distance_m"] <= 600:
                name = f"Near {nearest['name']}"
            else:
                name = f"{lat:.5f}, {lon:.5f}"
            detail = locality or ""
        elif locality and locality not in (detail or ""):
            detail = ", ".join(x for x in (detail, locality) if x)
        return {"name": name, "detail": detail, "lat": round(lat, 6), "lon": round(lon, 6), "locality": locality,
                "nearest_stop": nearest, "inside_delhi": self.inside_delhi(lat, lon), "source": source}

    # -- combined search
    def search(self, query: str, transit_places: list[dict], limit: int = 10, online: bool = True) -> list[dict]:
        q = norm(query)
        if len(q) < 2:
            return []
        tokens = q.split()

        def text_score(key: str):
            if key == q:
                return 0
            if key.startswith(q):
                return 1
            if f" {q}" in f" {key}":
                return 2
            if all(t in key for t in tokens):
                return 3
            return None

        scored = []
        for loc in self.localities:
            if not loc["searchable"]:
                continue
            s = text_score(loc["_key"])
            if s is not None:
                detail = "Locality" + (f" · centred on {loc['anchor']['name']} {'metro station' if loc['anchor']['mode'] == 'metro' else 'station' if loc['anchor']['mode'] == 'rail' else 'bus stop'}"
                                       if loc.get("anchor") else " (ward centre)")
                scored.append(((s, 0), {"id": f"loc:{loc['ward']}", "name": loc["name"], "detail": detail,
                                        "mode": "place", "kind": "Locality", "lat": loc["lat"], "lon": loc["lon"],
                                        "source": "Delhi ward map"}))
        for p in transit_places:
            s = text_score(p["_key"])
            if s is not None:
                rank = {"metro": 1, "rail": 2, "bus": 3}[p["mode"]]
                scored.append(((s, rank), {k: v for k, v in p.items() if not k.startswith("_")}))
        found = self.search_online(query, 8) if online else []
        for i, p in enumerate(found):
            s = text_score(norm(p["name"]))
            scored.append(((s if s is not None else 2, 0, i * 0.01), p))
        scored.sort(key=lambda x: x[0])
        out: list[dict] = []
        for _, p in scored:
            dup = any(norm(p["name"]) == norm(o["name"]) and haversine_km(p["lat"], p["lon"], o["lat"], o["lon"]) < 0.4
                      for o in out)
            if not dup:
                out.append(p)
            if len(out) >= limit:
                break
        return out
