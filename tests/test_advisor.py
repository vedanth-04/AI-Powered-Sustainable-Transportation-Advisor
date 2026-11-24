"""Tests for the Delhi multimodal advisor (routing, fares, budget logic, bus-model hook, API)."""

from __future__ import annotations

from datetime import datetime

import pytest

from advisor.bus_model import BusModel
from advisor.ingest import build_network, load_json
from advisor.network import BUS, METRO, RAIL, load_network
from advisor.planner import IST, Advisor, PlanError
from tests.advisor_fixtures import write_fixture

MONDAY_0700 = datetime(2026, 11, 23, 7, 0, tzinfo=IST)
SUNDAY_0700 = datetime(2026, 11, 22, 7, 0, tzinfo=IST)
ALPHA = {"lat": 28.600, "lon": 77.200, "label": "Alpha"}
CHARLIE = {"lat": 28.600, "lon": 77.260, "label": "Charlie"}
DELTA = {"lat": 28.640, "lon": 77.230, "label": "Delta"}
NORTH_POINT = {"lat": 28.5420, "lon": 77.2189, "label": "North Point"}
NEHRU_BUS = {"lat": 28.5470, "lon": 77.2494, "label": "Nehru Place"}


class NoModel(BusModel):
    def __init__(self):
        self.cfg = load_json("advisor_config.json")["bus_model"]
        self.active, self._sources, self._cache, self.parity = None, [], {}, None
        self.segment = None
        self.sources_status = [{"source": "all", "ok": False, "detail": "off in tests"}]


class _StubSource:
    name, version, typical_error, detail = "registry_champion", 2, 1.0, "stub champion"

    def __init__(self):
        self.calls = []

    def predict(self, entry):
        self.calls.append(entry)
        return 20.0


class StubModel(BusModel):
    """Behaves like the approved model but predicts a fixed 20 minutes for the full gate-to-gate segment."""

    def __init__(self):
        self.cfg = load_json("advisor_config.json")["bus_model"]
        self.segment = type("Seg", (), {"length_km": 2.63, "segment_id": self.cfg["segment_id"]})()
        self.src = _StubSource()
        self.active, self._sources, self._cache, self.parity = self.src, [self.src], {}, None
        self.sources_status = [{"source": "registry_champion", "ok": True, "version": 2, "detail": "stub"}]

    @property
    def calls(self):
        return self.src.calls


@pytest.fixture(scope="module")
def net(tmp_path_factory):
    root = tmp_path_factory.mktemp("advisor")
    raw = write_fixture(root / "raw")
    build_network(raw, root / "out", verify=False, log=lambda *_: None)
    return load_network(root / "out")


@pytest.fixture()
def advisor(net):
    return Advisor(net, NoModel(), online_places=False, online_routing=False)


def test_network_has_all_three_modes_and_drops_express_trains(net):
    modes = {p["mode"] for p in net.patterns}
    assert modes == {BUS, METRO, RAIL}
    rail = [p for p in net.patterns if p["mode"] == RAIL]
    assert [p["route_id"] for p in rail] == ["64001"]  # the superfast train is not a local passenger service
    assert "FAR AWAY" not in " ".join(net.names).upper()  # outside the Delhi service area


def test_official_bus_fare_is_attached(net):
    p = next(i for i, info in enumerate(net.patterns) if info.get("route_id") == "900")
    assert int(net.fare[p][0, 3]) == 10


def test_direct_metro_journey_and_slab_fare(advisor):
    result = advisor.plan(ALPHA, CHARLIE, MONDAY_0700, priority="fastest")
    metro = [j for j in result["journeys"] if j["modes"] == ["metro"]]
    assert metro, result["journeys"]
    j = metro[0]
    ride = next(l for l in j["legs"] if l["type"] == "ride")
    assert ride["distance_km"] == pytest.approx(6.0)
    assert j["fare_inr"] == 32  # 5-12 km slab (Aug 2025)
    assert ride["wait_minutes"] >= 0


def test_metro_interchange_is_one_ticket(advisor):
    result = advisor.plan(ALPHA, DELTA, MONDAY_0700, priority="fastest")
    j = next(j for j in result["journeys"] if j["modes"] == ["metro", "metro"])
    rides = [l for l in j["legs"] if l["type"] == "ride"]
    assert rides[1]["fare_inr"] == 0 and "same metro ticket" in rides[1]["fare_basis"]
    assert j["fare_inr"] == 32  # 3 km + 4.4 km = 7.4 km -> one 5-12 km fare
    assert j["metro_interchanges"] == 1
    # boarding the second line respects the interchange buffer
    t1 = datetime.strptime(rides[0]["arrive"], "%H:%M")
    t2 = datetime.strptime(rides[1]["depart"], "%H:%M")
    assert (t2 - t1).seconds >= 4 * 60 - 60


def test_sunday_slabs_and_weekend_note(advisor):
    result = advisor.plan(ALPHA, CHARLIE, SUNDAY_0700, priority="fastest")
    j = next(j for j in result["journeys"] if j["modes"] == ["metro"])
    assert j["fare_inr"] == 21
    assert any("weekday metro timetable" in n for n in result["notes"])


def test_budget_prefers_affordable_and_reports_shortfall(advisor):
    ok = advisor.plan(ALPHA, CHARLIE, MONDAY_0700, budget_inr=12)
    assert ok["budget_status"]["ok"]
    assert ok["journeys"][0]["fare_inr"] <= 12  # the Rs 10 train beats the Rs 32 metro
    assert "recommended" in ok["journeys"][0]["tags"]
    short = advisor.plan(ALPHA, CHARLIE, MONDAY_0700, budget_inr=5)
    assert not short["budget_status"]["ok"]
    assert short["budget_status"]["extra_needed_inr"] == 5
    assert all("over budget" in j["tags"] for j in short["journeys"])


def test_women_free_bus_fares(advisor):
    result = advisor.plan(ALPHA, DELTA, MONDAY_0700, priority="cheapest", women_free_bus=True)
    bus = [j for j in result["journeys"] if j["modes"] == ["bus"]]
    assert bus and bus[0]["fare_inr"] == 0


def test_every_leg_is_labelled_with_its_estimate_source(advisor):
    result = advisor.plan(ALPHA, DELTA, MONDAY_0700)
    for j in result["journeys"]:
        for leg in j["legs"]:
            assert leg["estimate_source"]
            if leg["type"] == "ride":
                assert leg["fare_basis"]
        assert j["why"]


def test_outside_delhi_and_no_stop_errors(advisor):
    with pytest.raises(PlanError) as err:
        advisor.plan({"lat": 27.0, "lon": 75.0}, CHARLIE, MONDAY_0700)
    assert err.value.code == "outside_delhi"
    with pytest.raises(PlanError) as err:
        advisor.plan({"lat": 28.80, "lon": 77.00}, CHARLIE, MONDAY_0700, modes=["bus", "metro", "rail"])
    assert err.value.code == "no_stop_near_origin"  # even after widening the walk to 2.5 km


def test_no_connection_late_at_night(advisor):
    with pytest.raises(PlanError) as err:
        advisor.plan(ALPHA, CHARLIE, datetime(2026, 11, 23, 23, 30, tzinfo=IST), modes=["bus", "metro", "rail"])
    assert err.value.code == "no_connection"


def test_bus_model_used_only_on_the_orr_corridor(net):
    stub = StubModel()
    adv = Advisor(net, stub, online_places=False, online_routing=False)
    result = adv.plan(NORTH_POINT, NEHRU_BUS, MONDAY_0700)
    bus = next(j for j in result["journeys"] if j["modes"] == ["bus"])
    leg = next(l for l in bus["legs"] if l["type"] == "ride")
    assert leg["bus_model"]["applied"]
    assert leg["bus_model"]["model_source"] == "registry_champion" and leg["bus_model"]["model_version"] == 2
    assert leg["bus_model"]["timetable_minutes"] == 7.0  # North Point -> Pumposh Enclave in the timetable
    assert leg["bus_model"]["model_minutes"] == pytest.approx(20.0 * leg["bus_model"]["segment_share"], abs=0.1)
    assert bus["uses_bus_model"]
    # metro-only journeys never call the model
    calls = len(stub.calls)
    adv.plan(ALPHA, CHARLIE, MONDAY_0700)
    assert len(stub.calls) == calls


def test_place_search_prefers_localities_and_anchors_them(advisor):
    results = advisor.search_places("bravo")
    assert results[0]["kind"] == "Locality" and results[0]["name"] == "Bravo Interchange"
    assert (results[0]["lat"], results[0]["lon"]) == (28.6, 77.23)  # centred on the same-named metro station
    assert sum(r["name"] == "Bravo Interchange" for r in results) == 1  # the same-named station is not repeated
    assert not advisor.search_places("ndmc")  # administrative charge areas are not offered as places
    point = advisor.search_places("28.6, 77.2")
    assert point[0]["kind"] == "Coordinates"


def test_boundary_and_reverse_geocoding(advisor):
    assert advisor.places.inside_delhi(28.6, 77.2)
    assert not advisor.places.inside_delhi(28.30, 77.20)
    r = advisor.reverse(28.6004, 77.2003)
    assert r["name"] == "Near Alpha Bus Stop" or r["name"].startswith("Near Alpha")
    assert r["inside_delhi"] and r["source"] == "offline"
    assert advisor.reverse(28.605, 77.235)["locality"] == "Bravo Interchange"


def test_walk_is_widened_when_no_stop_is_close(advisor):
    far = {"lat": 28.6000, "lon": 77.2140, "label": "Field"}  # ~1.3 km from Alpha
    result = advisor.plan(far, CHARLIE, MONDAY_0700)
    assert any("walks up to" in n for n in result["notes"])


def test_registry_champion_requires_a_valid_audit_chain(tmp_path):
    from advisor.bus_model import BusModel as Real
    cfg = load_json("advisor_config.json")
    reg = tmp_path / "outputs" / "phase3" / "registry"
    reg.mkdir(parents=True)
    (reg / "model_versions.json").write_text('{"aliases": {"champion": 2}, "versions": []}')
    (reg / "audit_log.jsonl").write_text('{"sequence": 1, "previous_sha256": "tampered", "entry_sha256": "x"}\n')
    model = Real(cfg, root=tmp_path)
    status = {s["source"]: s for s in model.sources_status}
    assert not status["registry_champion"]["ok"] and "audit chain broken" in status["registry_champion"]["detail"]
    assert not model.available or model.active.name != "registry_champion"


def test_api(net):
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient
    from advisor.server import create_app

    client = TestClient(create_app(advisor=Advisor(net, NoModel(), online_places=False, online_routing=False)))
    health = client.get("/api/health").json()
    assert health["status"] == "ready" and "geocoder" in health
    assert client.get("/api/reverse", params={"lat": 28.6, "lon": 77.2}).json()["inside_delhi"]
    assert client.get("/api/network").json()["boundary"]
    assert client.get("/api/places", params={"q": "alpha"}).json()["results"]
    r = client.post("/api/plan", json={"origin": ALPHA, "destination": CHARLIE, "depart": "2026-11-23T07:00", "budget_inr": 40})
    assert r.status_code == 200 and r.json()["journeys"]
    bad = client.post("/api/plan", json={"origin": {"lat": 27, "lon": 75}, "destination": CHARLIE})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "outside_delhi"


def test_offline_only_search_skips_the_online_geocoder(net):
    adv = Advisor(net, NoModel(), online_places=True)
    adv.places.search_online = lambda *a, **k: (_ for _ in ()).throw(AssertionError("online geocoder called"))
    assert adv.search_places("bravo", online=False)[0]["name"] == "Bravo Interchange"


# ---------------------------------------------------------------- cab mode
def _cab_fare(km, base=40, base_km=1.0, per_km=20):
    return round(base + max(0.0, km - base_km) * per_km)


def test_cab_only_option_uses_meter_fare_traffic_and_pickup(advisor):
    from advisor.geo import haversine_km
    result = advisor.plan(ALPHA, CHARLIE, MONDAY_0700)
    cab = next(j for j in result["journeys"] if j["modes"] == ["cab"])
    leg = cab["legs"][0]
    km = round(haversine_km(28.6, 77.2, 28.6, 77.26) * 1.35, 2)
    assert leg["distance_km"] == pytest.approx(km, abs=0.01)
    assert cab["fare_inr"] == _cab_fare(km)
    assert leg["cab"]["method"] == "rule" and leg["cab"]["traffic_factor"] == 1.3  # 07:00 falls in the 06-08 period
    assert leg["wait_minutes"] == 7  # assumed pickup wait for that period
    assert "indicative" in leg["fare_basis"]
    assert cab["co2_kg"] == pytest.approx(km * 0.15, abs=0.002)
    assert any("indicative" in n for n in result["notes"])


def test_night_charge_and_auto_rickshaw(advisor):
    night = advisor.plan(ALPHA, CHARLIE, datetime(2026, 11, 23, 23, 30, tzinfo=IST), cab_type="auto")
    leg = night["journeys"][0]["legs"][0]
    assert night["journeys"][0]["modes"] == ["cab"] and leg["mode_label"] == "Auto"
    km = leg["distance_km"]
    assert leg["fare_inr"] == round((30 + max(0, km - 1.5) * 11) * 1.25)
    assert "night charge" in leg["fare_basis"]


def test_modes_filter_excludes_cab_and_bus(advisor):
    result = advisor.plan(ALPHA, DELTA, MONDAY_0700, modes=["metro"])
    assert result["journeys"] and all(set(j["modes"]) == {"metro"} for j in result["journeys"])
    with pytest.raises(PlanError):
        advisor.plan(ALPHA, DELTA, MONDAY_0700, modes=["plane"])


def test_cab_first_mile_when_no_stop_is_walkable(advisor):
    far = {"lat": 28.60, "lon": 77.17, "label": "Far west"}  # about 3 km west of Alpha, nothing within 2.5 km
    result = advisor.plan(far, CHARLIE, MONDAY_0700, modes=["metro", "cab"])
    combos = [j for j in result["journeys"] if j["modes"][:1] == ["cab"] and "metro" in j["modes"]]
    assert combos, [j["modes"] for j in result["journeys"]]
    j = combos[0]
    cab, metro = j["legs"][0], next(l for l in j["legs"] if l["mode"] == "metro")
    assert cab["to"]["name"] == metro["from"]["name"] == "Alpha"
    assert j["fare_inr"] == cab["fare_inr"] + metro["fare_inr"]
    assert j["vehicle_changes"] == 1
