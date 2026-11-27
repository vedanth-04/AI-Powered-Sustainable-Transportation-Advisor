"""Journey planning: places, multimodal search, fares, CO2, budget-aware ranking and explanations."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from advisor.bus_model import BusModel
from advisor.cab import CabEstimate, CabRouter
from advisor.geo import haversine_km
from advisor.network import BUS, METRO, RAIL, MODE_NAMES, Network
from advisor.places import Gazetteer
from advisor.raptor import Leg, RawJourney, _buffer_sec, raptor

IST = timezone(timedelta(hours=5, minutes=30))
PROFILES = [
    ("all modes", {BUS, METRO, RAIL}),
    ("metro only", {METRO}),
    ("bus only", {BUS}),
    ("bus + metro", {BUS, METRO}),
    ("rail + metro", {RAIL, METRO}),
    ("rail + bus", {RAIL, BUS}),
]
PRIORITIES = {
    # weights per Rs, per minute, per transfer, per kg CO2, per 100 m walked
    "balanced": (1.0, 0.70, 5.0, 20.0, 0.6),
    "cheapest": (3.0, 0.10, 1.5, 5.0, 0.3),
    "fastest": (0.2, 1.00, 2.0, 5.0, 0.4),
    "greenest": (0.6, 0.25, 2.0, 120.0, 0.3),
}
MODE_LABEL = {BUS: "Bus", METRO: "Metro", RAIL: "Train"}
TRANSIT_MODE = {"bus": BUS, "metro": METRO, "rail": RAIL}
ALL_MODES = ("bus", "metro", "rail", "cab")
CAB_COLOR = {"taxi_ac": "#3B4256", "taxi_non_ac": "#3B4256", "auto": "#4C8C2B"}


class PlanError(ValueError):
    """A request the advisor cannot serve, with a user-facing explanation."""

    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


@dataclass
class Place:
    lat: float
    lon: float
    label: str


def _hhmm(sec: int) -> str:
    sec = int(sec)
    day, rem = divmod(sec, 86400)
    text = f"{rem // 3600:02d}:{rem % 3600 // 60:02d}"
    return text + (" (+1 day)" if day else "")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


class Advisor:
    def __init__(self, net: Network, bus_model: BusModel | None = None, gazetteer: Gazetteer | None = None,
                 online_places: bool | None = None, online_routing: bool = True):
        self.net = net
        self.cfg = net.config
        self.cab = CabRouter(self.cfg, online=online_routing)
        self.bus_model = bus_model if bus_model is not None else BusModel(self.cfg)
        self._places = self._build_places()
        if gazetteer is None:
            gazetteer = Gazetteer(net.data_dir / "places.json", self.cfg,
                                  stops=[p for p in self._places if p["mode"] in ("metro", "rail")] +
                                        [p for p in self._places if p["mode"] == "bus"], online=online_places)
        self.places = gazetteer

    # ------------------------------------------------------------------ places
    def _build_places(self) -> list[dict]:
        net = self.net
        groups: dict[tuple, list[int]] = {}
        for i, name in enumerate(net.names):
            key = (_norm(re.sub(r"\([A-Z]+\)$", "", name)), int(net.mode[i]))
            groups.setdefault(key, []).append(i)
        places = []
        for (key, mode), members in groups.items():
            # split same-name stops that are far apart (different places)
            clusters: list[list[int]] = []
            for i in members:
                for c in clusters:
                    if haversine_km(net.lat[i], net.lon[i], net.lat[c[0]], net.lon[c[0]]) < 0.5:
                        c.append(i)
                        break
                else:
                    clusters.append([i])
            for c in clusters:
                label = {METRO: "Delhi Metro station", RAIL: "Railway station", BUS: "Bus stop"}[mode]
                places.append({"id": f"stop:{c[0]}", "name": net.names[c[0]], "mode": MODE_NAMES[mode],
                               "detail": label, "kind": label, "source": "transit timetable",
                               "lat": round(float(np.mean(net.lat[c])), 6), "lon": round(float(np.mean(net.lon[c])), 6),
                               "stops": len(c), "_key": _norm(net.names[c[0]])})
        order = {"metro": 0, "rail": 1, "bus": 2}
        places.sort(key=lambda p: (order[p["mode"]], p["name"]))
        return places

    def search_places(self, query: str, limit: int = 10, online: bool = True) -> list[dict]:
        coord = self._parse_coords(query)
        if coord:
            r = self.places.reverse(*coord, online=online)
            return [{"id": f"pt:{coord[0]:.6f},{coord[1]:.6f}", "name": r["name"], "detail": r["detail"] or "Map point",
                     "mode": "place", "kind": "Coordinates", "lat": coord[0], "lon": coord[1], "source": r["source"]}]
        return self.places.search(query, self._places, limit, online=online)

    def reverse(self, lat: float, lon: float, online: bool = True) -> dict:
        return self.places.reverse(lat, lon, online=online)

    @staticmethod
    def _parse_coords(text: str):
        m = re.fullmatch(r"\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*", text or "")
        return (float(m.group(1)), float(m.group(2))) if m else None

    def resolve(self, spec: dict, role: str) -> Place:
        if not isinstance(spec, dict):
            raise PlanError("bad_place", f"Choose a {role} from the suggestions or type coordinates like 28.6139, 77.2090.")
        lat, lon = spec.get("lat"), spec.get("lon")
        if lat is None or lon is None:
            raise PlanError("bad_place", f"The {role} has no coordinates.")
        lat, lon = float(lat), float(lon)
        if not self.places.inside_delhi(lat, lon):
            raise PlanError("outside_delhi",
                            f"The {role} ({lat:.4f}, {lon:.4f}) is outside Delhi (NCT boundary).",
                            "This advisor covers places inside the National Capital Territory of Delhi only.")
        return Place(lat, lon, str(spec.get("label") or spec.get("name") or f"{lat:.5f}, {lon:.5f}"))

    # ------------------------------------------------------------------ bus-model corridor helpers
    def _corridor_patterns(self):
        if not hasattr(self, "_corr"):
            self._corr = []
            if self.bus_model.segment is not None:
                for p, info in enumerate(self.net.patterns):
                    if info["mode"] != BUS:
                        continue
                    seq = self.net.pat_stops[p]
                    run = self.bus_model.corridor_run([float(self.net.lat[s]) for s in seq], [float(self.net.lon[s]) for s in seq])
                    if run:
                        self._corr.append((p, run))
        return self._corr

    def corridor_timetable_minutes(self) -> float | None:
        """Median timetable time for the full gate-to-gate segment across the bus routes that use it."""
        vals = []
        for p, (i, j) in self._corridor_patterns():
            seq = self.net.pat_stops[p]
            span = haversine_km(self.net.lat[seq[i]], self.net.lon[seq[i]], self.net.lat[seq[j]], self.net.lon[seq[j]])
            t = float(np.median(self.net.arr[p][:, j] - self.net.dep_t[p][i, :])) / 60
            if span > 0.5:
                vals.append(t * self.bus_model.segment.length_km / span)
        return round(float(np.median(vals)), 1) if vals else None

    def corridor_geometry(self) -> dict | None:
        if not self._corridor_patterns():
            return None
        p, (i, j) = max(self._corridor_patterns(), key=lambda x: x[1][1] - x[1][0])
        seq = self.net.pat_stops[p][i:j + 1]
        routes = sorted({self.net.patterns[q]["route"].split(" ")[0] for q, _ in self._corridor_patterns()})
        return {"segment": self.cfg["bus_model"]["segment_id"], "path": [[float(self.net.lat[s]), float(self.net.lon[s])] for s in seq],
                "routes": routes}

    # ------------------------------------------------------------------ access
    def _walk(self, metres: float) -> int:
        w = self.cfg["walking"]
        return int(math.ceil(metres * w["detour_factor"] / (w["speed_kmh"] / 3.6)))

    def _access(self, place: Place, max_walk_m: float) -> dict[int, tuple[int, float]]:
        out = {}
        per_mode: dict[int, int] = {}
        for s, d in self.net.nearby(place.lat, place.lon, max_walk_m):
            m = int(self.net.mode[s])
            if per_mode.get(m, 0) >= (30 if m == BUS else 6):
                continue
            per_mode[m] = per_mode.get(m, 0) + 1
            out[s] = (self._walk(d), d)
        return out

    def _access_expanding(self, place: Place, max_walk: float, role: str, notes: list) -> dict:
        radii = [max_walk] + [r for r in self.cfg["walking"].get("auto_expand_m", []) if r > max_walk]
        for radius in radii:
            stops = self._access(place, radius)
            if stops:
                if radius > max_walk:
                    nearest = min(m for _, m in stops.values())
                    notes.append(f"No stop within {max_walk:.0f} m of the {role}; the nearest is about {nearest:.0f} m away, "
                                 f"so walks up to {radius:.0f} m were allowed.")
                return stops
        code = "no_stop_near_origin" if role == "starting point" else "no_stop_near_destination"
        raise PlanError(code, f"No bus stop, metro or rail station within {radii[-1]:.0f} m of the {role}.",
                        "Choose a point closer to a main road or a metro station.")

    # ------------------------------------------------------------------ plan
    def plan(self, origin: dict, destination: dict, depart: datetime, budget_inr: float | None = None,
             priority: str = "balanced", women_free_bus: bool = False, smart_card: bool = False,
             max_walk_m: float | None = None, modes: list[str] | None = None, cab_type: str = "taxi_ac") -> dict:
        if priority not in PRIORITIES:
            raise PlanError("bad_priority", f"priority must be one of {sorted(PRIORITIES)}")
        if budget_inr is not None and budget_inr < 0:
            raise PlanError("bad_budget", "The budget cannot be negative.")
        allowed = set(modes) if modes else set(ALL_MODES)
        if not allowed or not allowed <= set(ALL_MODES):
            raise PlanError("bad_modes", "Choose at least one of bus, metro, train and cab.")
        if cab_type not in self.cfg["cab"]["types"]:
            raise PlanError("bad_cab_type", f"cab_type must be one of {sorted(self.cfg['cab']['types'])}")
        transit = {TRANSIT_MODE[m] for m in allowed if m in TRANSIT_MODE}
        use_cab = "cab" in allowed
        o, d = self.resolve(origin, "starting point"), self.resolve(destination, "destination")
        straight = haversine_km(o.lat, o.lon, d.lat, d.lon)
        if straight < 0.3:
            raise PlanError("too_close", f"The two places are only {straight * 1000:.0f} m apart - walking is the best option.")
        depart = depart.astimezone(IST) if depart.tzinfo else depart.replace(tzinfo=IST)
        max_walk = float(max_walk_m or self.cfg["walking"]["max_access_m"])
        walk_notes: list[str] = []
        acc, egr = {}, {}
        if transit:
            for role, place in (("starting point", o), ("destination", d)):
                try:
                    stops = self._access_expanding(place, max_walk, role, walk_notes)
                except PlanError:
                    if not use_cab:
                        raise
                    stops = {}
                    walk_notes.append(f"No stop or station is within walking distance of the {role}, so a cab leg connects it.")
                if role == "starting point":
                    acc = stops
                else:
                    egr = stops
        dow = depart.weekday()
        t0 = depart.hour * 3600 + depart.minute * 60
        active, notes = self.net.active_patterns(dow)
        raw: dict[tuple, tuple[RawJourney, str]] = {}

        def run(name, a, e, m):
            if not a or not e or not m:
                return
            for j in raptor(self.net, a, e, t0, active, m):
                sig = tuple((l.kind, l.pattern, l.board_pos, l.alight_pos, l.from_stop, l.to_stop)
                            for l in j.legs if l.kind in ("ride", "cab"))
                if any(l.kind == "ride" for l in j.legs) and sig not in raw:
                    raw[sig] = (j, name)

        seen_sets = set()
        for name, pmodes in PROFILES:
            eff = frozenset(pmodes & transit)
            if eff and eff not in seen_sets:
                seen_sets.add(eff)
                run(name, acc, egr, set(eff))

        cab_access: dict[int, CabEstimate] = {}
        cab_egress: dict[int, CabEstimate] = {}
        cab_only: CabEstimate | None = None
        if use_cab:
            rail_like = transit & {METRO, RAIL}
            feeders_o = self._feeders(o, rail_like) if rail_like else []
            feeders_d = self._feeders(d, rail_like) if rail_like else []
            ests = self.cab.one_to_many((o.lat, o.lon), [(self.net.lat[s], self.net.lon[s]) for s in feeders_o] + [(d.lat, d.lon)], t0)
            cab_only = ests[-1]
            cab_access = dict(zip(feeders_o, ests[:-1]))
            egress_clock = t0 + int(straight * 180)  # rough time the last leg starts
            cab_egress = dict(zip(feeders_d, self.cab.many_to_one([(self.net.lat[s], self.net.lon[s]) for s in feeders_d],
                                                                 (d.lat, d.lon), egress_clock)))
            run("cab + metro/train", {s: (e.total_sec, e.km * 1000, "cab") for s, e in cab_access.items()}, egr, rail_like)
            run("metro/train + cab", acc, {s: (e.total_sec, e.km * 1000, "cab") for s, e in cab_egress.items()}, rail_like)
            if not raw and not acc:
                # no walkable stop at the start: still offer cab + transit to a walkable end
                pass

        journeys = [self._enrich(j, profile, depart, t0, o, d, women_free_bus, smart_card, cab_access, cab_egress, cab_type)
                    for j, profile in raw.values()]
        journeys = [j for j in journeys if j is not None]
        cab_notes = []
        if cab_only is not None:
            min_cab_km = self.cfg["cab"]["min_cab_km"]
            if cab_only.km >= min_cab_km:
                journeys.append(self._cab_only_journey(o, d, cab_only, t0, cab_type))
            else:
                cab_notes.append(f"Direct cab estimates are available for trips of at least {min_cab_km:g} km by road.")
        if not journeys:
            if cab_notes:
                raise PlanError("no_connection", cab_notes[0], "Try a longer trip or allow public transport.")
            raise PlanError("no_connection",
                            f"No connection found leaving at {depart:%H:%M} within the next "
                            f"{self.cfg['router']['search_window_min'] // 60} hours with the modes you allowed.",
                            "Metro runs roughly 05:00-23:30 and most buses stop late at night; try an earlier time or allow cabs.")
        result = self._rank(journeys, budget_inr, priority)
        self._attach_cab_paths(result["journeys"])
        car_km = straight * self.cfg["emissions_kg_per_pkm"]["route_detour"]["car"]
        cab_notes.extend(self._cab_notes(result["journeys"]))
        return {
            "query": {"origin": o.__dict__, "destination": d.__dict__, "depart": depart.isoformat(), "weekday": depart.strftime("%A"),
                      "budget_inr": budget_inr, "priority": priority, "women_free_bus": women_free_bus,
                      "smart_card": smart_card, "max_walk_m": max_walk, "modes": sorted(allowed), "cab_type": cab_type},
            "straight_line_km": round(straight, 2),
            "car_baseline_kg_co2": round(car_km * self.cfg["emissions_kg_per_pkm"]["car_baseline"], 3),
            "notes": walk_notes + notes + self._fare_notes(dow, women_free_bus, smart_card) + cab_notes,
            **result,
        }

    # ------------------------------------------------------------------ cab helpers
    def _feeders(self, place: Place, modes: set[int]) -> list[int]:
        """Metro/rail stations worth a cab ride: beyond walking range, within the feeder limit, nearest first."""
        c = self.cfg["cab"]
        cands = [(s, m) for s, m in self.net.nearby(place.lat, place.lon, c["feeder_max_km"] * 1000)
                 if int(self.net.mode[s]) in modes and m >= c["min_cab_km"] * 1000 / 1.35]
        return [s for s, _ in cands[: c["feeder_stations"]]]

    def _cab_label(self, cab_type: str) -> str:
        return "Auto" if cab_type == "auto" else "Cab"

    def _cab_leg(self, est: CabEstimate, frm: dict, to: dict, depart: int, cab_type: str) -> dict:
        t = self.cfg["cab"]["types"][cab_type]
        fare, basis = self.cab.fare(est.km, cab_type, depart + est.pickup_sec)
        if est.method == "osrm":
            src = (f"Road route from OSRM (OpenStreetMap): {est.free_flow_sec / 60:.0f} min free-flow x traffic factor "
                   f"{est.traffic_factor:g}; pickup wait {est.pickup_sec // 60} min (assumed)")
        else:
            f = self.cfg["cab"]["fallback"]
            src = (f"Rule: straight line x {f['road_detour_factor']:g} at {f['free_flow_speed_kmh']} km/h x traffic factor "
                   f"{est.traffic_factor:g}; pickup wait {est.pickup_sec // 60} min (assumed)")
        return {
            "type": "ride", "mode": "cab", "mode_label": self._cab_label(cab_type), "route": t["label"],
            "towards": to["name"], "agency": "Taxi or app cab" if cab_type != "auto" else "Auto-rickshaw",
            "color": CAB_COLOR.get(cab_type, "#3B4256"), "from": frm, "to": to,
            "depart": _hhmm(depart), "arrive": _hhmm(depart + est.total_sec),
            "wait_minutes": round(est.pickup_sec / 60, 1), "minutes": round(est.drive_sec / 60, 1),
            "stops": 0, "distance_km": round(est.km, 2), "fare_inr": fare, "fare_basis": basis, "fare_unit": "cab",
            "co2_kg": round(self.cab.co2(est.km, cab_type), 3), "estimate_source": src, "bus_model": None,
            "path": [[frm["lat"], frm["lon"]], [to["lat"], to["lon"]]], "stop_names": [frm["name"], to["name"]],
            "cab": {"method": est.method, "pickup_min": est.pickup_sec // 60, "drive_min": round(est.drive_sec / 60, 1),
                    "free_flow_min": round(est.free_flow_sec / 60, 1), "traffic_factor": est.traffic_factor,
                    "type": cab_type, "type_label": t["label"], "path_is_road": False},
        }

    def _cab_only_journey(self, o: Place, d: Place, est: CabEstimate, t0: int, cab_type: str) -> dict:
        leg = self._cab_leg(est, self._point(None, o), self._point(None, d), t0, cab_type)
        arrive = t0 + est.total_sec
        return {
            "profile": "cab only", "leave": _hhmm(t0), "arrive": _hhmm(arrive), "duration_min": round(est.total_sec / 60, 1),
            "wait_after_departure_min": 0.0, "fare_inr": leg["fare_inr"], "rides": 1, "transfers": 0, "vehicle_changes": 0,
            "metro_interchanges": 0, "modes": ["cab"], "walk_m": 0, "co2_kg": leg["co2_kg"], "uses_bus_model": False,
            "legs": [leg], "_arrive_sec": arrive, "_leave_sec": t0,
        }

    def _attach_cab_paths(self, journeys: list[dict]) -> None:
        """Replace straight placeholder lines with road paths for the cab legs that are shown."""
        legs = [l for j in journeys for l in j["legs"] if l.get("mode") == "cab"]
        if not legs or self.cab.status["state"] != "ready":
            return
        from concurrent.futures import ThreadPoolExecutor

        keys = {}
        for l in legs:
            keys.setdefault(((l["from"]["lat"], l["from"]["lon"]), (l["to"]["lat"], l["to"]["lon"])), []).append(l)
        with ThreadPoolExecutor(max_workers=3) as pool:
            paths = dict(zip(keys, pool.map(lambda k: self.cab.route_path(*k), list(keys))))
        for k, path in paths.items():
            if path and len(path) >= 2:
                for l in keys[k]:
                    l["path"] = path
                    l["cab"]["path_is_road"] = True

    def _cab_notes(self, journeys: list[dict]) -> list[str]:
        cab_legs = [l for j in journeys for l in j["legs"] if l.get("mode") == "cab"]
        if not cab_legs:
            return []
        methods = {l["cab"]["method"] for l in cab_legs}
        if methods == {"osrm"}:
            how = "Cab times use OpenStreetMap road routing (OSRM) stretched by a Delhi traffic factor for the time of day."
        else:
            how = ("Road routing was not reachable, so cab times use a straight-line rule (distance x 1.35 at an assumed speed) "
                   "and a traffic factor.")
        return [how + " Cab fares are Delhi meter fares and are indicative: app cabs price dynamically, and cab "
                      "availability is not checked."]

    def _fare_notes(self, dow: int, women: bool, card: bool) -> list[str]:
        notes = []
        if dow == 6:
            notes.append("Sunday metro fare slabs applied (DMRC national holiday/Sunday fares; other national holidays are not detected).")
        if women:
            notes.append("Bus fares set to ₹0: women travel free on DTC and cluster buses (pink ticket).")
        if card:
            notes.append("Metro fares include the 10% smart-card discount (off-peak extra discount not applied).")
        return notes

    # ------------------------------------------------------------------ journey details
    def _enrich(self, j: RawJourney, profile, depart, t0, o: Place, d: Place, women, card,
                cab_access=None, cab_egress=None, cab_type="taxi_ac") -> dict | None:
        net, cfg = self.net, self.cfg
        cab_access, cab_egress = cab_access or {}, cab_egress or {}
        legs = [Leg(**l.__dict__) for l in j.legs]
        model_info = self._apply_bus_model(legs, depart, t0)
        if model_info is False:
            return None
        rides = [l for l in legs if l.kind == "ride"]
        # leave as late as possible: first boarding minus buffer and access walk
        first = rides[0]
        first_mode = net.patterns[first.pattern]["mode"]
        access = legs[0] if legs[0].kind in ("walk", "cab") and legs[0].from_stop is None else None
        buffer = _buffer_sec(net, ("access",), first_mode)
        walk_sec = (access.arrive - access.depart) if access else 0
        leave = max(t0, first.depart - buffer - walk_sec)
        if access:
            access.depart, access.arrive = leave, leave + walk_sec
        out_legs, ready = [], leave
        fares = self._fares(rides, depart.weekday(), women, card)
        total_co2 = 0.0
        total_walk = 0.0
        cab_fares = 0.0
        modes_seq: list[str] = []
        for idx, leg in enumerate(legs):
            if leg.kind == "cab":
                est = cab_access.get(leg.to_stop) if leg.from_stop is None else cab_egress.get(leg.from_stop)
                if est is None:
                    return None
                frm = self._point(leg.from_stop, o)
                to = self._point(leg.to_stop, d)
                start = leg.depart if leg.from_stop is None else max(leg.depart, ready)
                out = self._cab_leg(est, frm, to, start, cab_type)
                out["wait_minutes"] = round(est.pickup_sec / 60, 1)
                out_legs.append(out)
                cab_fares += out["fare_inr"]
                total_co2 += out["co2_kg"]
                modes_seq.append("cab")
                ready = start + est.total_sec
                continue
            if leg.kind == "walk":
                if leg.walk_m < 60:
                    continue
                total_walk += leg.walk_m
                out_legs.append({
                    "type": "walk",
                    "from": self._point(leg.from_stop, o), "to": self._point(leg.to_stop, d),
                    "depart": _hhmm(leg.depart), "arrive": _hhmm(leg.arrive),
                    "minutes": round((leg.arrive - leg.depart) / 60, 1), "distance_m": round(leg.walk_m),
                    "estimate_source": "rule: straight line x %.1f detour at %.1f km/h" % (
                        cfg["walking"]["detour_factor"], cfg["walking"]["speed_kmh"]),
                    "path": [[p["lat"], p["lon"]] for p in (self._point(leg.from_stop, o), self._point(leg.to_stop, d))],
                })
                ready = leg.arrive
                continue
            info = net.patterns[leg.pattern]
            mode = info["mode"]
            seq = net.pat_stops[leg.pattern][leg.board_pos:leg.alight_pos + 1]
            km = float(net.pat_km[leg.pattern][leg.alight_pos] - net.pat_km[leg.pattern][leg.board_pos])
            factor = cfg["emissions_kg_per_pkm"][MODE_NAMES[mode]]
            co2 = km * factor
            total_co2 += co2
            wait = max(0, leg.depart - ready)
            fare = fares["per_leg"][rides.index(leg)]
            src = {BUS: "GTFS timetable (OTD; constant-speed schedule estimate)",
                   METRO: "DMRC GTFS timetable (OTD)",
                   RAIL: "Indian Railways timetable (DataMeet 2016)"}[mode]
            extra = model_info.get(id(leg)) if model_info else None
            if extra and extra.get("applied"):
                src += f" + bus model v{extra['model_version']} on the Outer Ring Road stretch"
            out_legs.append({
                "type": "ride", "mode": MODE_NAMES[mode], "mode_label": MODE_LABEL[mode],
                "route": re.sub(r"\.(?=\s|$)", "", info["route"]), "towards": info.get("towards") or net.names[int(net.pat_stops[leg.pattern][-1])],
                "agency": info["agency"], "color": info["color"],
                "from": self._point(int(seq[0])), "to": self._point(int(seq[-1])),
                "depart": _hhmm(leg.depart), "arrive": _hhmm(leg.arrive),
                "wait_minutes": round(wait / 60, 1), "minutes": round((leg.arrive - leg.depart) / 60, 1),
                "stops": len(seq) - 1, "distance_km": round(km, 2),
                "fare_inr": fare["inr"], "fare_basis": fare["basis"], "fare_unit": fare["unit"],
                "co2_kg": round(co2, 3), "estimate_source": src, "bus_model": extra,
                "path": [[float(net.lat[s]), float(net.lon[s])] for s in seq],
                "stop_names": [net.names[int(s)] for s in seq],
            })
            modes_seq.append(MODE_NAMES[mode])
            ready = leg.arrive
        out_legs = self._merge_walks(out_legs)
        arrive = max(legs[-1].arrive, ready)
        vehicles = len(modes_seq)
        return {
            "profile": profile, "leave": _hhmm(leave), "arrive": _hhmm(arrive),
            "duration_min": round((arrive - leave) / 60, 1), "wait_after_departure_min": round((leave - t0) / 60, 1),
            "fare_inr": round(fares["total"] + cab_fares, 1), "rides": vehicles, "transfers": vehicles - 1,
            "vehicle_changes": vehicles - 1, "metro_interchanges": fares["metro_interchanges_free"],
            "modes": modes_seq,
            "walk_m": round(total_walk), "co2_kg": round(total_co2, 3),
            "uses_bus_model": bool(model_info), "legs": out_legs,
            "_arrive_sec": arrive, "_leave_sec": leave,
        }

    @staticmethod
    def _merge_walks(legs: list[dict]) -> list[dict]:
        """A transfer walk followed by the final walk (or two transfer walks) reads as one walk."""
        out: list[dict] = []
        for leg in legs:
            if out and leg["type"] == "walk" and out[-1]["type"] == "walk":
                prev = out[-1]
                prev["to"] = leg["to"]
                prev["arrive"] = leg["arrive"]
                prev["minutes"] = round(prev["minutes"] + leg["minutes"], 1)
                prev["distance_m"] = prev["distance_m"] + leg["distance_m"]
                prev["path"] = prev["path"] + leg["path"][1:]
                continue
            out.append(leg)
        return out

    def _point(self, stop: int | None, place: Place | None = None) -> dict:
        if stop is None:
            return {"name": place.label, "lat": place.lat, "lon": place.lon, "kind": "place"}
        return {"name": self.net.names[stop], "lat": float(self.net.lat[stop]), "lon": float(self.net.lon[stop]),
                "kind": MODE_NAMES[int(self.net.mode[stop])]}

    # ------------------------------------------------------------------ fares
    def _slab(self, km: float, slabs: list, prices: list) -> int:
        for limit, price in zip(slabs, prices):
            if km <= limit:
                return int(price)
        return int(prices[-1])

    def _fares(self, rides: list[Leg], dow: int, women: bool, card: bool) -> dict:
        net, f = self.net, self.cfg["fares"]
        per_leg, total, free_interchanges = [], 0, 0
        i = 0
        while i < len(rides):
            leg = rides[i]
            info = net.patterns[leg.pattern]
            km = float(net.pat_km[leg.pattern][leg.alight_pos] - net.pat_km[leg.pattern][leg.board_pos])
            if info["mode"] == METRO:
                # consecutive metro rides changing at the same station stay inside the paid area: one fare
                j, unit_km = i, km
                while (j + 1 < len(rides) and net.patterns[rides[j + 1].pattern]["mode"] == METRO
                       and rides[j + 1].from_stop == rides[j].to_stop):
                    j += 1
                    nxt = rides[j]
                    unit_km += float(net.pat_km[nxt.pattern][nxt.alight_pos] - net.pat_km[nxt.pattern][nxt.board_pos])
                table = f["metro"]["sunday_holiday_inr"] if dow == 6 else f["metro"]["weekday_inr"]
                price = self._slab(unit_km, f["metro"]["slabs_km"], table)
                if card:
                    price = round(price * 0.9, 1)
                basis = f"DMRC slab for {unit_km:.1f} km" + (" (Sunday)" if dow == 6 else "") + (" - 10% smart card" if card else "")
                if any(net.patterns[rides[x].pattern]["line_key"] == "ORANGE/AIRPORT" for x in range(i, j + 1)):
                    basis += "; Airport Express may cost more"
                per_leg.append({"inr": price, "basis": basis, "unit": f"metro-{i}"})
                for x in range(i + 1, j + 1):
                    per_leg.append({"inr": 0, "basis": "same metro ticket (interchange inside the station)", "unit": f"metro-{i}"})
                    free_interchanges += 1
                total += price
                i = j + 1
                continue
            if info["mode"] == BUS:
                official = int(net.fare[leg.pattern][leg.board_pos, leg.alight_pos]) if net.fare[leg.pattern] is not None else 0
                if women and f["bus"]["women_free"]:
                    price, basis = 0, "free for women (pink ticket)"
                elif official > 0:
                    price, basis = official, "official stage fare (OTD fare_rules)"
                else:
                    price = self._slab(km, f["bus"]["fallback_slabs_km"], f["bus"]["fallback_inr"])
                    basis = f"DTC non-AC slab for {km:.1f} km (no stage fare in feed)"
            else:
                price = self._slab(km, f["rail"]["slabs_km"], f["rail"]["inr"])
                basis = f"unreserved second-class ordinary fare, {km:.1f} km (assumed)"
            per_leg.append({"inr": price, "basis": basis, "unit": f"{MODE_NAMES[info['mode']]}-{i}"})
            total += price
            i += 1
        return {"per_leg": per_leg, "total": round(total, 1), "metro_interchanges_free": free_interchanges}

    # ------------------------------------------------------------------ bus model
    def _apply_bus_model(self, legs: list[Leg], depart: datetime, t0: int):
        """Replace the scheduled time of the ORR eastbound stretch with the model's estimate, then re-time."""
        bm, net = self.bus_model, self.net
        if not bm.available:
            return {}
        info = {}
        changed = False
        for leg in legs:
            if leg.kind != "ride" or net.patterns[leg.pattern]["mode"] != BUS:
                continue
            seq = net.pat_stops[leg.pattern][leg.board_pos:leg.alight_pos + 1]
            run = bm.corridor_run([float(net.lat[s]) for s in seq], [float(net.lon[s]) for s in seq])
            if not run:
                continue
            a, b = leg.board_pos + run[0], leg.board_pos + run[1]
            sched = int(net.arr[leg.pattern][leg.trip, b] - net.dep_t[leg.pattern][a, leg.trip])
            entry_sec = int(net.dep_t[leg.pattern][a, leg.trip])
            day0 = depart.replace(hour=0, minute=0, second=0, microsecond=0)
            entry = day0 + timedelta(seconds=entry_sec)
            try:
                minutes, share, source, version = bm.segment_minutes(
                    entry, net.lat[seq[run[0]]], net.lon[seq[run[0]]], net.lat[seq[run[1]]], net.lon[seq[run[1]]])
            except Exception as exc:  # keep the timetable if the model fails
                info[id(leg)] = {"applied": False, "reason": f"{type(exc).__name__}"}
                continue
            delta = int(round(minutes * 60)) - sched
            leg.arrive += delta
            changed = True
            err = bm.active.typical_error if bm.active is not None else None
            info[id(leg)] = {"applied": True, "segment": bm.cfg["segment_id"], "model_version": version, "model_source": source,
                             "from": net.names[int(seq[run[0]])], "to": net.names[int(seq[run[1]])],
                             "entry_time": entry.strftime("%H:%M"),
                             "model_minutes": round(minutes, 1), "timetable_minutes": round(sched / 60, 1),
                             "segment_share": round(share, 2), "path_range": [int(run[0]), int(run[1])],
                             "typical_error_min": round(err * share, 1) if err else None}
        if changed and not self._retime(legs):
            return False
        return info

    def _retime(self, legs: list[Leg]) -> bool:
        """Propagate a changed arrival: later rides take the next trip of the same pattern if needed."""
        net = self.net
        ready, prev_label = None, ("access",)
        for leg in legs:
            if ready is None:
                ready = leg.arrive
                prev_label = ("access",) if leg.kind == "walk" else ("ride", leg.pattern)
                continue
            if leg.kind in ("walk", "cab"):
                dur = leg.arrive - leg.depart
                leg.depart = max(leg.depart, ready)
                leg.arrive = leg.depart + dur
                ready = leg.arrive
                continue
            mode = net.patterns[leg.pattern]["mode"]
            need = ready + _buffer_sec(net, prev_label, mode) if prev_label[0] == "ride" else ready
            if leg.depart < need:
                col = net.dep_t[leg.pattern][leg.board_pos]
                t = int(np.searchsorted(col, need, side="left"))
                if t >= len(col):
                    return False
                leg.trip = t
                leg.depart = int(col[t])
                leg.arrive = int(net.arr[leg.pattern][t, leg.alight_pos])
            ready = leg.arrive
            prev_label = ("ride", leg.pattern)
        return True

    # ------------------------------------------------------------------ ranking
    def _rank(self, journeys: list[dict], budget, priority) -> dict:
        # identical-looking journeys (same rides, same times) from different timetable patterns: keep one
        seen, unique = set(), []
        for j in sorted(journeys, key=lambda j: (j["_arrive_sec"], j["fare_inr"])):
            sig = tuple((l["route"], l["from"]["name"], l["to"]["name"], l["depart"]) for l in j["legs"] if l["type"] == "ride")
            if sig not in seen:
                seen.add(sig)
                unique.append(j)
        journeys = unique
        # drop journeys that are worse or equal on every criterion than another one
        keep = []
        for a in journeys:
            if a["profile"] == "cab only":  # always shown, so a door-to-door cab can be compared with public transport
                keep.append(a)
                continue
            dominated = False
            for b in journeys:
                if a is b:
                    continue
                better_eq = (b["_arrive_sec"] <= a["_arrive_sec"] and b["fare_inr"] <= a["fare_inr"]
                             and b["vehicle_changes"] <= a["vehicle_changes"] and b["co2_kg"] <= a["co2_kg"] + 1e-9
                             and b["walk_m"] <= a["walk_m"] + 50)
                strictly = (b["_arrive_sec"] < a["_arrive_sec"] or b["fare_inr"] < a["fare_inr"]
                            or b["vehicle_changes"] < a["vehicle_changes"] or b["co2_kg"] < a["co2_kg"] - 1e-9)
                if better_eq and strictly:
                    dominated = True
                    break
            if not dominated:
                keep.append(a)
        w = PRIORITIES[priority]

        def score(j):
            return (w[0] * j["fare_inr"] + w[1] * j["duration_min"] + w[2] * j["vehicle_changes"]
                    + w[3] * j["co2_kg"] + w[4] * j["walk_m"] / 100)

        for j in keep:
            j["score"] = round(score(j), 2)
            j["within_budget"] = budget is None or j["fare_inr"] <= budget + 1e-9
        within = [j for j in keep if j["within_budget"]]
        pool = within if within else keep
        pool.sort(key=lambda j: j["score"])
        others = sorted([j for j in keep if j not in pool], key=lambda j: j["fare_inr"])
        # Reserve one cab slot for the direct comparison, even when cheaper feeders rank first.
        cab_cap = self.cfg["cab"].get("max_cab_options", 3)
        direct_cab = next((j for j in keep if j["profile"] == "cab only"), None) if cab_cap > 0 else None
        mixed_cab_slots = cab_cap - int(direct_cab is not None)
        ordered = []
        for j in pool + others:
            if "cab" in j["modes"] and j is not direct_cab:
                if mixed_cab_slots <= 0:
                    continue
                mixed_cab_slots -= 1
            ordered.append(j)
        ordered = ordered[: self.cfg["router"]["max_results"]]
        if not ordered:
            return {"journeys": [], "budget_status": None}
        if direct_cab is not None and all(j is not direct_cab for j in ordered):
            ordered[-1] = direct_cab
        cheapest = min(keep, key=lambda j: (j["fare_inr"], j["_arrive_sec"]))
        fastest = min(keep, key=lambda j: (j["_arrive_sec"], j["fare_inr"]))
        fewest = min(keep, key=lambda j: (j["vehicle_changes"], j["_arrive_sec"]))
        greenest = min(keep, key=lambda j: (j["co2_kg"], j["_arrive_sec"]))
        for rank, j in enumerate(ordered):
            tags = []
            if rank == 0 and j["within_budget"]:
                tags.append("recommended")
            for tag, ref in (("cheapest", cheapest), ("fastest", fastest), ("fewest changes", fewest), ("lowest CO2", greenest)):
                if j is ref:
                    tags.append(tag)
            if not j["within_budget"]:
                tags.append("over budget")
            j["tags"] = tags
            j["why"] = self._explain(j, rank, ordered, budget, priority, cheapest, fastest)
            j["id"] = f"j{rank + 1}"
        status = None
        if budget is not None:
            if within:
                status = {"ok": True, "message": f"{len(within)} option(s) cost ₹{budget:g} or less."}
            else:
                status = {"ok": False, "message": (f"No option fits ₹{budget:g}. The cheapest costs ₹{cheapest['fare_inr']:g}, "
                                                    f"₹{cheapest['fare_inr'] - budget:g} more than your budget."),
                          "cheapest_fare_inr": cheapest["fare_inr"], "extra_needed_inr": round(cheapest["fare_inr"] - budget, 1)}
        for j in ordered:
            j.pop("_arrive_sec", None); j.pop("_leave_sec", None)
        return {"journeys": ordered, "budget_status": status}

    def _explain(self, j, rank, ordered, budget, priority, cheapest, fastest) -> list[str]:
        why = []
        label = {"bus": "Bus", "metro": "Metro", "rail": "Train"}
        cab_leg = next((l for l in j["legs"] if l.get("mode") == "cab"), None)
        if cab_leg:
            label["cab"] = cab_leg["mode_label"]
        modes = " + ".join(dict.fromkeys(label[m] for m in j["modes"]))
        if rank == 0 and j["within_budget"]:
            why.append(f"Best {priority} score among the options" + (f" within your ₹{budget:g} budget." if budget is not None else "."))
        if j is cheapest:
            why.append(f"Lowest fare: ₹{j['fare_inr']:g}.")
        elif j["fare_inr"] > cheapest["fare_inr"]:
            why.append(f"Costs ₹{j['fare_inr'] - cheapest['fare_inr']:g} more than the cheapest option.")
        if j is fastest:
            why.append(f"Fastest arrival ({j['arrive']}).")
        else:
            gap = round(j["duration_min"] - fastest["duration_min"])
            if gap > 0:
                why.append(f"About {gap} min slower than the fastest option.")
            elif gap < 0:
                why.append(f"Shorter door-to-door time than the fastest-arriving option (it leaves later).")
        if j["vehicle_changes"] == 0:
            why.append(f"No change of vehicle ({modes}).")
        else:
            why.append(f"{j['vehicle_changes']} change(s): {modes}.")
        if j["uses_bus_model"]:
            why.append("Includes the bus-model estimate for the Outer Ring Road stretch.")
        if cab_leg:
            why.append(f"{cab_leg['mode_label']} fare is an indicative meter fare; pickup time is an assumption and availability is not checked.")
        if budget is not None and not j["within_budget"]:
            why.append(f"Over budget by ₹{j['fare_inr'] - budget:g}.")
        return why
