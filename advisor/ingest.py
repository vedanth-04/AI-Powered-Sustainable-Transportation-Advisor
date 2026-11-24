"""Build the advisor's multimodal network from the pinned Delhi datasets.

Inputs (data/raw/transit/, fetched by scripts/advisor_fetch_data.py):
  otd_bus/  OTD Delhi bus GTFS (DTC + DIMTS), with official stage fares
  dmrc/     OTD Delhi Metro GTFS
  rail/     DataMeet Indian Railways stations/trains/schedules

Output (data/processed/advisor/): network.npz (arrays) + network_meta.json.
Times are seconds after midnight of the service day; distances are km.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from advisor.geo import haversine_km, haversine_km_vec

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = Path(__file__).resolve().parent / "config"
RAW_DIR = ROOT / "data" / "raw" / "transit"
OUT_DIR = ROOT / "data" / "processed" / "advisor"

BUS, METRO, RAIL = 0, 1, 2
MODE_NAMES = {BUS: "bus", METRO: "metro", RAIL: "rail"}
ALL_DAYS = 0b1111111  # bit 0 = Monday ... bit 6 = Sunday
PASSENGER_TYPES = {"Pass", "MEMU", "DEMU", "EMU"}
RAIL_EXCLUDE = {"DSAP", "DSBC", "DSBP", "TKDC", "TKEC", "SQK"}  # block cabins / mis-geocoded


def load_json(name: str) -> dict:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def _hms(series: pd.Series) -> np.ndarray:
    parts = series.str.split(":", expand=True).astype(int)
    return (parts[0] * 3600 + parts[1] * 60 + parts[2]).to_numpy(np.int32)


def _in_area(lat, lon, area) -> np.ndarray:
    return ((lat >= area["lat_min"]) & (lat <= area["lat_max"])
            & (lon >= area["lon_min"]) & (lon <= area["lon_max"]))


def verify_sources(raw_dir: Path = RAW_DIR) -> dict:
    """sha256 of every pinned file; raises if one is missing or differs."""
    sources = load_json("sources.json")["datasets"]
    report = {}
    for key, ds in sources.items():
        for name, expected in ds["files"].items():
            path = raw_dir / key / name
            if not path.exists():
                raise FileNotFoundError(f"{path} is missing; run python -m scripts.advisor_fetch_data")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError(f"{path} does not match the pinned sha256")
            report[f"{key}/{name}"] = expected
    return report


# --------------------------------------------------------------------------- patterns

class PatternBuilder:
    """Collects trips, groups them into FIFO stop patterns (RAPTOR routes)."""

    def __init__(self):
        self.groups: dict[tuple, list] = defaultdict(list)
        self.info: dict[tuple, dict] = {}

    def add(self, key: tuple, stops: tuple, arr: np.ndarray, dep: np.ndarray, info: dict):
        full = key + (stops,)
        self.groups[full].append((arr, dep))
        self.info.setdefault(full, info)

    def build(self):
        """Yield (info, stops, arr_matrix, dep_matrix) with FIFO trips."""
        for full, trips in self.groups.items():
            trips.sort(key=lambda t: int(t[1][0]))
            lanes: list[list] = []
            for trip in trips:
                for lane in lanes:  # first lane the trip does not overtake
                    last = lane[-1]
                    if np.all(trip[1] >= last[1]) and np.all(trip[0] >= last[0]):
                        lane.append(trip)
                        break
                else:
                    lanes.append([trip])
            for lane in lanes:
                arr = np.vstack([t[0] for t in lane]).astype(np.int32)
                dep = np.vstack([t[1] for t in lane]).astype(np.int32)
                yield self.info[full], full[-1], arr, dep


# --------------------------------------------------------------------------- per mode

def read_bus(raw: Path, area: dict, stops_out: list, builder: PatternBuilder):
    d = raw / "otd_bus"
    stops = pd.read_csv(d / "stops.txt", dtype={"stop_id": str})
    stops = stops[_in_area(stops.stop_lat, stops.stop_lon, area)]
    index = {}
    for row in stops.itertuples(index=False):
        index[row.stop_id] = len(stops_out)
        stops_out.append({"mode": BUS, "src": f"bus:{row.stop_id}", "name": str(row.stop_name).strip(),
                          "lat": float(row.stop_lat), "lon": float(row.stop_lon)})
    routes = pd.read_csv(d / "routes.txt", dtype=str).set_index("route_id")
    trips = pd.read_csv(d / "trips.txt", dtype=str)
    st = pd.read_csv(d / "stop_times.txt", dtype={"trip_id": str, "stop_id": str},
                     usecols=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"])
    st = st[st.stop_id.isin(index)]
    st = st.sort_values(["trip_id", "stop_sequence"], kind="stable")
    st["arr"] = _hms(st.arrival_time)
    st["dep"] = _hms(st.departure_time)
    st["s"] = st.stop_id.map(index).astype(np.int32)
    trip_route = trips.set_index("trip_id").route_id
    for trip_id, g in st.groupby("trip_id", sort=False):
        if len(g) < 2:
            continue
        route_id = trip_route.get(trip_id)
        if route_id is None:
            continue
        r = routes.loc[route_id]
        name = str(r.route_long_name)
        builder.add((BUS, route_id, ALL_DAYS), tuple(g.s.tolist()), g.arr.to_numpy(), g.dep.to_numpy(),
                    {"mode": BUS, "route_id": route_id, "route": display_bus_route(name),
                     "agency": str(r.agency_id), "days": ALL_DAYS, "color": "#2e7d32" if r.agency_id == "DTC" else "#00897b",
                     "raw_name": name})


def display_bus_route(raw_name: str) -> str:
    """'764MSTLDOWN' -> '764M (STL) down'."""
    name = raw_name
    direction = ""
    for suffix in ("DOWN", "UP"):
        if name.endswith(suffix):
            name, direction = name[: -len(suffix)], suffix.lower()
            break
    tags = []
    for tag in ("STL", "EXT", "LNK", "SPL"):
        if tag in name:
            name = name.replace(tag, "")
            tags.append(tag)
    label = name.strip() or raw_name
    if tags:
        label += f" ({'/'.join(tags)})"
    return f"{label} {direction}".strip()


def read_metro(raw: Path, area: dict, cfg: dict, stops_out: list, builder: PatternBuilder):
    d = raw / "dmrc"
    stops = pd.read_csv(d / "stops.txt", dtype={"stop_id": str})
    stops = stops[_in_area(stops.stop_lat, stops.stop_lon, area)]
    index = {}
    for row in stops.itertuples(index=False):
        index[row.stop_id] = len(stops_out)
        stops_out.append({"mode": METRO, "src": f"metro:{row.stop_id}", "name": str(row.stop_name).strip(),
                          "lat": float(row.stop_lat), "lon": float(row.stop_lon)})
    routes = pd.read_csv(d / "routes.txt", dtype=str).set_index("route_id")
    cal = pd.read_csv(d / "calendar.txt", dtype=str).set_index("service_id")
    days = {sid: sum(int(cal.loc[sid, day]) << i for i, day in enumerate(
        ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])) for sid in cal.index}
    trips = pd.read_csv(d / "trips.txt", dtype=str).set_index("trip_id")
    st = pd.read_csv(d / "stop_times.txt", dtype={"trip_id": str, "stop_id": str})
    st = st[st.stop_id.isin(index)].sort_values(["trip_id", "stop_sequence"], kind="stable")
    st["arr"] = _hms(st.arrival_time)
    st["dep"] = _hms(st.departure_time)
    st["s"] = st.stop_id.map(index).astype(np.int32)
    st["km"] = st.shape_dist_traveled.astype(float) / 1000.0
    lines = cfg["metro_lines"]
    for trip_id, g in st.groupby("trip_id", sort=False):
        if len(g) < 2 or trip_id not in trips.index:
            continue
        t = trips.loc[trip_id]
        long_name = str(routes.loc[t.route_id, "route_long_name"])
        key, _, towards = long_name.partition("_")
        line = lines.get(key, {"name": key.title(), "color": "#607d8b"})
        mask = days.get(t.service_id, 0)
        builder.add((METRO, t.route_id, mask), tuple(g.s.tolist()), g.arr.to_numpy(), g.dep.to_numpy(),
                    {"mode": METRO, "route_id": t.route_id, "route": line["name"], "towards": towards.split(" to ")[-1].strip(),
                     "agency": "DMRC", "days": mask, "color": line["color"], "line_key": key,
                     "km": tuple(np.round(g.km.to_numpy() - g.km.iloc[0], 3).tolist()), "raw_name": long_name})


def read_rail(raw: Path, area: dict, stops_out: list, builder: PatternBuilder):
    d = raw / "rail"
    stations = json.loads((d / "stations.json").read_text(encoding="utf-8"))["features"]
    index = {}
    for f in stations:
        g = f.get("geometry") or {}
        coords = g.get("coordinates")
        p = f["properties"]
        if not coords or p["code"] in RAIL_EXCLUDE:
            continue
        lon, lat = coords[:2]
        state = p.get("state")
        if state in ("Haryana", "Uttar Pradesh", "Punjab"):
            continue
        if _in_area(np.array([lat]), np.array([lon]), area)[0]:
            index[p["code"]] = len(stops_out)
            stops_out.append({"mode": RAIL, "src": f"rail:{p['code']}", "name": f"{p['name'].title()} ({p['code']})",
                              "lat": float(lat), "lon": float(lon)})
    trains = {t["properties"]["number"]: t["properties"]
              for t in json.loads((d / "trains.json").read_text(encoding="utf-8"))["features"]}
    rows = defaultdict(list)
    for s in json.loads((d / "schedules.json").read_text(encoding="utf-8")):
        if s["station_code"] in index and trains.get(s["train_number"], {}).get("type") in PASSENGER_TYPES:
            rows[s["train_number"]].append(s)

    def clock(value, day):
        if not value or value == "None":
            return None
        h, m, sec = (int(x) for x in value.split(":"))
        return (int(day or 1) - 1) * 86400 + h * 3600 + m * 60 + sec

    for number, sched in rows.items():
        sched.sort(key=lambda r: r["id"])
        seq, arr, dep = [], [], []
        for r in sched:
            a, b = clock(r["arrival"], r["day"]), clock(r["departure"], r["day"])
            a = b if a is None else a
            b = a if b is None else b
            if a is None:
                continue
            if seq and index[r["station_code"]] == seq[-1]:
                continue
            seq.append(index[r["station_code"]]); arr.append(a); dep.append(max(a, b))
        if len(seq) < 2:
            continue
        arr = np.array(arr, dtype=np.int64); dep = np.array(dep, dtype=np.int64)
        for i in range(1, len(arr)):  # overnight wrap inside a day-less record
            while arr[i] < dep[i - 1]:
                arr[i:] += 86400; dep[i:] += 86400
        shift = (dep[0] // 86400) * 86400
        arr -= shift; dep -= shift
        t = trains[number]
        lat = np.array([stops_out[s]["lat"] for s in seq]); lon = np.array([stops_out[s]["lon"] for s in seq])
        km = np.concatenate([[0.0], np.cumsum(haversine_km_vec(lat[:-1], lon[:-1], lat[1:], lon[1:]))])
        builder.add((RAIL, number, ALL_DAYS), tuple(seq), arr, dep,
                    {"mode": RAIL, "route_id": number, "route": f"{number} {t['name']}", "agency": f"Indian Railways ({t.get('zone') or 'NR'})",
                     "days": ALL_DAYS, "color": "#6d4c41", "towards": str(t.get("to_station_name", "")).title(),
                     "train_type": t.get("type"), "km": tuple(np.round(km, 3).tolist()), "raw_name": t["name"]})


def bus_fare_table(raw: Path) -> pd.DataFrame:
    d = raw / "otd_bus"
    rules = pd.read_csv(d / "fare_rules.txt", dtype=str)
    prices = pd.read_csv(d / "fare_attributes.txt", usecols=["fare_id", "price"], dtype={"fare_id": str})
    table = rules.merge(prices, on="fare_id")
    table["price"] = table.price.astype(float).round().clip(0, 255).astype(np.uint8)
    return table[["route_id", "origin_id", "destination_id", "price"]]


# --------------------------------------------------------------------------- assemble

def build_network(raw_dir: Path = RAW_DIR, out_dir: Path = OUT_DIR, *, verify: bool = True, log=print) -> dict:
    cfg = load_json("advisor_config.json")
    area = cfg["service_area"]
    hashes = verify_sources(raw_dir) if verify else {}
    stops: list[dict] = []
    builder = PatternBuilder()
    log("reading bus GTFS ...");   read_bus(raw_dir, area, stops, builder)
    log("reading metro GTFS ..."); read_metro(raw_dir, area, cfg, stops, builder)
    log("reading rail timetable ..."); read_rail(raw_dir, area, stops, builder)

    lat = np.array([s["lat"] for s in stops]); lon = np.array([s["lon"] for s in stops])
    mode = np.array([s["mode"] for s in stops], dtype=np.int8)

    log("grouping trips into FIFO patterns ...")
    pat_info, pat_stops, pat_km, arr_blocks, dep_blocks = [], [], [], [], []
    for info, seq, arr, dep in builder.build():
        seq = np.array(seq, dtype=np.int32)
        if "km" in info:
            km = np.array(info["km"], dtype=np.float32)
        else:
            km = np.concatenate([[0.0], np.cumsum(haversine_km_vec(lat[seq[:-1]], lon[seq[:-1]], lat[seq[1:]], lon[seq[1:]])
                                                  * cfg["emissions_kg_per_pkm"]["route_detour"]["bus"])]).astype(np.float32)
        meta = {k: v for k, v in info.items() if k != "km"}
        meta["n_trips"] = int(arr.shape[0])
        pat_info.append(meta); pat_stops.append(seq); pat_km.append(km)
        arr_blocks.append(arr.ravel()); dep_blocks.append(dep.ravel())

    n_pat = len(pat_info)
    stop_off = np.zeros(n_pat + 1, dtype=np.int64); stop_off[1:] = np.cumsum([len(s) for s in pat_stops])
    time_off = np.zeros(n_pat + 1, dtype=np.int64); time_off[1:] = np.cumsum([len(b) for b in arr_blocks])

    log("attaching official bus stage fares ...")
    fare_off = np.zeros(n_pat + 1, dtype=np.int64)
    fare_blocks = []
    fares = bus_fare_table(raw_dir)
    fare_groups = {rid: g for rid, g in fares.groupby("route_id", sort=False)}
    src_of = [s["src"] for s in stops]
    for p, info in enumerate(pat_info):
        n = len(pat_stops[p])
        if info["mode"] != BUS:
            fare_off[p + 1] = fare_off[p]
            continue
        matrix = np.zeros((n, n), dtype=np.uint8)
        g = fare_groups.get(info["route_id"])
        if g is not None:
            pos = {}
            for i, s in enumerate(pat_stops[p]):
                pos.setdefault(src_of[s].split(":", 1)[1], i)
            o = g.origin_id.map(pos); dd = g.destination_id.map(pos)
            ok = o.notna() & dd.notna()
            oi = o[ok].astype(int).to_numpy(); di = dd[ok].astype(int).to_numpy()
            fwd = oi < di
            matrix[oi[fwd], di[fwd]] = g.price[ok].to_numpy()[fwd]
        fare_blocks.append(matrix.ravel())
        fare_off[p + 1] = fare_off[p] + n * n

    log("computing walking transfers ...")
    walk = cfg["walking"]
    max_km = walk["max_transfer_m"] / 1000.0
    cell = max_km / 111.0
    grid = defaultdict(list)
    for i in range(len(stops)):
        grid[(int(lat[i] / cell), int(lon[i] / cell))].append(i)
    fp_from, fp_to, fp_sec = [], [], []
    speed = walk["speed_kmh"] / 3600.0
    for (gx, gy), members in grid.items():
        cand = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grid.get((gx + dx, gy + dy), ())]
        cand = np.array(cand)
        for i in members:
            dist = haversine_km_vec(lat[i], lon[i], lat[cand], lon[cand])
            keep = (dist <= max_km) & (cand != i)
            for j, dkm in zip(cand[keep], dist[keep]):
                fp_from.append(i); fp_to.append(int(j)); fp_sec.append(int(math.ceil(dkm * walk["detour_factor"] / speed)))
    order = np.lexsort((fp_to, fp_from))
    fp_from = np.array(fp_from, dtype=np.int32)[order]; fp_to = np.array(fp_to, dtype=np.int32)[order]
    fp_sec = np.array(fp_sec, dtype=np.int32)[order]
    fp_off = np.zeros(len(stops) + 1, dtype=np.int64)
    np.add.at(fp_off, fp_from + 1, 1); fp_off = np.cumsum(fp_off)

    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_dir / "network.npz",
        stop_lat=lat, stop_lon=lon, stop_mode=mode,
        pat_stop_off=stop_off, pat_stops=np.concatenate(pat_stops).astype(np.int32),
        pat_km=np.concatenate(pat_km).astype(np.float32),
        pat_time_off=time_off, pat_arr=np.concatenate(arr_blocks).astype(np.int32),
        pat_dep=np.concatenate(dep_blocks).astype(np.int32),
        pat_fare_off=fare_off, pat_fare=np.concatenate(fare_blocks) if fare_blocks else np.zeros(0, np.uint8),
        fp_off=fp_off, fp_to=fp_to, fp_sec=fp_sec,
    )
    shapes = metro_shapes(raw_dir, cfg)
    counts = {MODE_NAMES[m]: int((mode == m).sum()) for m in MODE_NAMES}
    pat_counts = {MODE_NAMES[m]: sum(1 for p in pat_info if p["mode"] == m) for m in MODE_NAMES}
    trip_counts = {MODE_NAMES[m]: sum(p["n_trips"] for p in pat_info if p["mode"] == m) for m in MODE_NAMES}
    meta = {"stops": [{"name": s["name"], "src": s["src"]} for s in stops], "patterns": pat_info,
            "metro_shapes": shapes, "counts": {"stops": counts, "patterns": pat_counts, "trips": trip_counts},
            "source_sha256": hashes, "sources": load_json("sources.json")["datasets"]}
    (out_dir / "network_meta.json").write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")
    from advisor.places import build_places

    place_counts = build_places(raw_dir, out_dir)
    meta["counts"]["places"] = place_counts
    (out_dir / "network_meta.json").write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")
    log(f"network: stops {counts}, trips {trip_counts}, walking links {len(fp_to)}, places {place_counts}")
    return meta["counts"]


def metro_shapes(raw: Path, cfg: dict) -> list[dict]:
    """One simplified polyline per metro line for the map background."""
    d = raw / "dmrc"
    shapes = pd.read_csv(d / "shapes.txt", dtype={"shape_id": str})
    trips = pd.read_csv(d / "trips.txt", dtype=str)
    routes = pd.read_csv(d / "routes.txt", dtype=str).set_index("route_id")
    trips["key"] = trips.route_id.map(lambda r: str(routes.loc[r, "route_long_name"]).split("_")[0])
    out, seen = [], set()
    for (key, shape_id), _ in trips.groupby(["key", "shape_id"]):
        g = shapes[shapes.shape_id == shape_id].sort_values("shape_pt_sequence")
        if len(g) < 2 or key == "AQUA":  # Noida Metro (NMRC) is not part of the Delhi data
            continue
        sig = (key, round(g.shape_pt_lat.iloc[0], 3), round(g.shape_pt_lat.iloc[-1], 3))
        rev = (key, sig[2], sig[1])
        if sig in seen or rev in seen:
            continue
        seen.add(sig)
        step = max(1, len(g) // 150)
        pts = g.iloc[::step][["shape_pt_lat", "shape_pt_lon"]].round(5).to_numpy().tolist()
        pts.append([round(g.shape_pt_lat.iloc[-1], 5), round(g.shape_pt_lon.iloc[-1], 5)])
        line = cfg["metro_lines"].get(key, {"name": key, "color": "#607d8b"})
        out.append({"line": line["name"], "color": line["color"], "points": pts})
    return out
