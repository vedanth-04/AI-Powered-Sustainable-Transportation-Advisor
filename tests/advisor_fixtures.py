"""A tiny hand-made network in the same file formats as the real Delhi feeds.

Used only by the unit tests; the advisor itself only runs on the pinned public datasets.
"""

from __future__ import annotations

import json
from pathlib import Path


def _hms(sec: int) -> str:
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def write_fixture(raw: Path) -> Path:
    bus, metro, rail, places = raw / "otd_bus", raw / "dmrc", raw / "rail", raw / "places"
    for d in (bus, metro, rail, places):
        d.mkdir(parents=True, exist_ok=True)

    # ---- metro: line RED M1-M2-M3 (east), line BLUE M2-M4 (north)
    (metro / "agency.txt").write_text("agency_id,agency_name,agency_url,agency_timezone\nDMRC,DMRC,http://x,Asia/Kolkata\n")
    (metro / "calendar.txt").write_text(
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "weekday,1,1,1,1,1,0,0,20190101,20251231\n")
    (metro / "stops.txt").write_text(
        "stop_id,stop_code,stop_name,stop_desc,stop_lat,stop_lon\n"
        "1,,Alpha,,28.600,77.200\n2,,Bravo Interchange,,28.600,77.230\n3,,Charlie,,28.600,77.260\n4,,Delta,,28.640,77.230\n")
    (metro / "routes.txt").write_text(
        "route_id,agency_id,route_short_name,route_long_name,route_desc,route_type\n"
        "0,,R,RED_Alpha to Charlie,,1\n1,,B,BLUE_Bravo Interchange to Delta,,1\n")
    trips, times, shapes = ["route_id,service_id,trip_id,trip_headsign,trip_short_name,direction_id,block_id,shape_id"], \
        ["trip_id,arrival_time,departure_time,stop_id,stop_sequence,stop_headsign,pickup_type,drop_off_type,shape_dist_traveled"], \
        ["shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled"]
    n = 0
    for start in range(6 * 3600, 9 * 3600, 600):
        trips.append(f"0,weekday,{n},,,,,shpR")
        for seq, (stop, off, dist) in enumerate([(1, 0, 0), (2, 300, 3000), (3, 600, 6000)]):
            times.append(f"{n},{_hms(start + off)},{_hms(start + off + 20)},{stop},{seq},,0,0,{dist}")
        n += 1
        trips.append(f"1,weekday,{n},,,,,shpB")
        for seq, (stop, off, dist) in enumerate([(2, 0, 0), (4, 400, 4400)]):
            times.append(f"{n},{_hms(start + 120 + off)},{_hms(start + 140 + off)},{stop},{seq},,0,0,{dist}")
        n += 1
    shapes += ["shpR,28.6,77.2,1,0", "shpR,28.6,77.26,2,6000", "shpB,28.6,77.23,1,0", "shpB,28.64,77.23,2,4400"]
    (metro / "trips.txt").write_text("\n".join(trips) + "\n")
    (metro / "stop_times.txt").write_text("\n".join(times) + "\n")
    (metro / "shapes.txt").write_text("\n".join(shapes) + "\n")

    # ---- bus: route 900 rides the ORR eastbound corridor; route 901 runs Alpha-area -> Delta-area slowly
    (bus / "agency.txt").write_text("agency_id,agency_name,agency_url,agency_timezone,agency_lang,agency_phone,agency_fare_url\nDTC,DTC,http://x,Asia/Kolkata,en,,\n")
    (bus / "calendar.txt").write_text("start_date,end_date,monday,tuesday,wednesday,thursday,friday,saturday,sunday,service_id\n20240101,20270101,1,1,1,1,1,1,1,1\n")
    (bus / "stops.txt").write_text(
        "stop_code,stop_id,stop_lat,stop_lon,stop_name,zone_id\n"
        "X,10,28.5420,77.2189,North Point,10\nX,11,28.5423,77.2248,Swami Nagar,11\nX,12,28.5437,77.2438,Pumposh Enclave,12\n"
        "X,13,28.5470,77.2494,Nehru Place Bus,13\nX,20,28.6005,77.2005,Alpha Bus Stop,20\nX,21,28.6400,77.2305,Delta Bus Stop,21\n")
    (bus / "routes.txt").write_text("agency_id,route_id,route_long_name,route_short_name,route_type\nDTC,900,900UP,,3\nDTC,901,901DOWN,,3\n")
    btrips, btimes = ["route_id,service_id,trip_id,shape_id"], ["trip_id,arrival_time,departure_time,stop_id,stop_sequence"]
    for start in range(6 * 3600, 9 * 3600, 900):
        tid = f"900_{start}"
        btrips.append(f"900,1,{tid},")
        for seq, (stop, off) in enumerate([(10, 0), (11, 120), (12, 420), (13, 600)]):
            btimes.append(f"{tid},{_hms(start + off)},{_hms(start + off)},{stop},{seq}")
        tid = f"901_{start}"
        btrips.append(f"901,1,{tid},")
        for seq, (stop, off) in enumerate([(20, 0), (21, 3000)]):
            btimes.append(f"{tid},{_hms(start + off)},{_hms(start + off)},{stop},{seq}")
    (bus / "trips.txt").write_text("\n".join(btrips) + "\n")
    (bus / "stop_times.txt").write_text("\n".join(btimes) + "\n")
    (bus / "fare_rules.txt").write_text("fare_id,route_id,origin_id,destination_id\nF1,900,10,13\nF2,901,20,21\n")
    (bus / "fare_attributes.txt").write_text("fare_id,price,currency_type,payment_method,transfers,agency_id,old_fare_id\nF1,10.0,INR,0,0,DTC,F1\nF2,15.0,INR,0,0,DTC,F2\n")

    # ---- rail: one passenger train Alpha Rail -> Charlie Rail
    stations = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.2008, 28.6008]}, "properties": {"code": "ARL", "name": "ALPHA RAIL", "state": "Delhi NCT"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.2595, 28.6005]}, "properties": {"code": "CRL", "name": "CHARLIE RAIL", "state": "Delhi NCT"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [75.0, 27.0]}, "properties": {"code": "FAR", "name": "FAR AWAY", "state": "Rajasthan"}},
    ]}
    trains = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": None, "properties": {"number": "64001", "name": "Alpha Charlie EMU", "type": "Pass", "zone": "NR", "to_station_name": "CHARLIE RAIL"}},
        {"type": "Feature", "geometry": None, "properties": {"number": "12001", "name": "Express", "type": "SF", "zone": "NR", "to_station_name": "FAR AWAY"}},
    ]}
    schedules = [
        {"train_number": "64001", "station_code": "ARL", "arrival": "None", "departure": "07:20:00", "day": 1, "id": 1},
        {"train_number": "64001", "station_code": "CRL", "arrival": "07:28:00", "departure": "None", "day": 1, "id": 2},
        {"train_number": "12001", "station_code": "ARL", "arrival": "None", "departure": "06:00:00", "day": 1, "id": 3},
        {"train_number": "12001", "station_code": "CRL", "arrival": "06:05:00", "departure": "06:06:00", "day": 1, "id": 4},
    ]
    (rail / "stations.json").write_text(json.dumps(stations))
    (rail / "trains.json").write_text(json.dumps(trains))
    (rail / "schedules.json").write_text(json.dumps(schedules))

    # ---- places: a square "Delhi" boundary and two wards
    def square(lat0, lon0, lat1, lon1):
        return [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]
    boundary = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"Id": 0},
                "geometry": {"type": "Polygon", "coordinates": square(28.45, 76.95, 28.85, 77.35)}}]}
    wards = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"Ward_Name": "BRAVO INTERCHANGE", "Ward_No": "1"},
         "geometry": {"type": "Polygon", "coordinates": square(28.59, 77.22, 28.62, 77.25)}},
        {"type": "Feature", "properties": {"Ward_Name": "EMPTY  FIELDS", "Ward_No": "2"},
         "geometry": {"type": "Polygon", "coordinates": square(28.78, 76.98, 28.82, 77.02)}},
        {"type": "Feature", "properties": {"Ward_Name": "NDMC CHARGE 1", "Ward_No": "3"},
         "geometry": {"type": "Polygon", "coordinates": square(28.62, 77.19, 28.64, 77.21)}},
    ]}
    (places / "Delhi_Boundary.geojson").write_text(json.dumps(boundary))
    (places / "Delhi_Wards.geojson").write_text(json.dumps(wards))
    return raw
