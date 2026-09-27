"""V3: provenance, source health, failure visibility, scheduler, environment classification, isolation.

Weather tests use real Open-Meteo responses recorded on 27 Sep 2026 (see fixtures/README.md).
Mandi tests use the clearly-labelled synthetic fixture: no real mandi response could be recorded
from the build sandbox, so the parser is tested against the documented schema only.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import InventoryItem, IngestionRun, MarketPrice, Warehouse, WeatherObservation
from app.models.enums import DataOrigin, RunStatus, RunTrigger, WeatherKind
from app.services.data import connectors, freshness, indicators
from app.services.data import scheduler as sched
from app.services.data.sources import OGD_MANDI, OPEN_METEO, get_source

FIX = Path(__file__).parent / "fixtures"
REAL = {name: json.loads((FIX / f"open_meteo_v3_{name}.json").read_text()) for name in ("bengaluru", "kolar", "mysuru")}
OGD = json.loads((FIX / "ogd_mandi_synthetic.json").read_text())
RECORDED_AT = datetime.fromtimestamp(REAL["bengaluru"]["current"]["time"], UTC)  # 27 Sep 2026 11:15 IST
TODAY = date(2026, 9, 27)
FAKE_KEY = "test-key-0123456789"
COORDS = {"blr": (12.97, 77.59, "bengaluru"), "hyd": (13.14, 78.13, "kolar")}


@pytest.fixture
def http(monkeypatch):
    calls: list[httpx.Request] = []
    state = {"handler": lambda req: httpx.Response(500), "calls": calls}

    def make_client():
        def handler(req):
            calls.append(req)
            return state["handler"](req)
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(connectors, "make_client", make_client)
    monkeypatch.setattr(connectors, "today_ist", lambda: TODAY)
    monkeypatch.setattr(freshness, "today_ist", lambda: TODAY)
    state["now"] = RECORDED_AT + timedelta(minutes=5)
    monkeypatch.setattr(connectors, "utcnow", lambda: state["now"])
    return state


@pytest.fixture
def ogd_key():
    s = get_settings()
    old = s.data_gov_in_api_key
    s.data_gov_in_api_key = FAKE_KEY
    yield
    s.data_gov_in_api_key = old


def real_weather(req: httpx.Request) -> httpx.Response:
    """Serve the recorded response for whichever warehouse location was requested."""
    lat = float(req.url.params["latitude"])
    name = min(COORDS.values(), key=lambda c: abs(c[0] - lat))[2]
    return httpx.Response(200, json=REAL[name])


def set_coords(world):
    for k, (lat, lon, _) in COORDS.items():
        r = world["admin"].patch(f"/api/warehouses/{world['warehouses'][k]['id']}", {"latitude": lat, "longitude": lon})
        assert r.status_code == 200, r.text


def fetch(api, key):
    r = api.post(f"/api/data/sources/{key}/runs")
    assert r.status_code == 202, r.text
    return api.get(f"/api/data/runs/{r.json()['id']}").json()


def source(api, key):
    return next(s for s in api.get("/api/data/sources").json() if s["key"] == key)


# --------------------------------------------------------------------------- weather: real recorded responses


def test_real_weather_ingestion_stores_provenance_and_forecast_separately(world, http, db):
    set_coords(world)
    http["handler"] = real_weather
    run = fetch(world["admin"], OPEN_METEO)
    assert run["status"] == "SUCCESS", run
    assert run["rows_inserted"] == 16 and run["rows_rejected"] == 0  # 2 × (current + 7 completed days)
    assert run["params"]["forecast_days_stored"] == 6  # 2 × (today + 2 days) — kept apart from observations
    assert run["endpoint"] == get_settings().open_meteo_base and run["scope"] == "ORGANIZATION"
    assert run["warnings"] == 0  # the recorded reading is 5 minutes old: not stale

    obs = db.scalars(select(WeatherObservation).where(WeatherObservation.kind == WeatherKind.CURRENT)).all()
    assert len(obs) == 2
    for o in obs:
        assert o.run_id and o.source_endpoint.startswith(get_settings().open_meteo_base)
        assert o.raw_reference["observed_at"] == RECORDED_AT.isoformat()
        assert o.validation_status.value == "ACCEPTED" and o.fetched_at is not None

    cur = {w["warehouse"]["name"]: w for w in world["admin"].get("/api/weather/current").json()}
    blr = cur["BLR Central"]
    assert blr["reading"]["temperature_c"] == REAL["bengaluru"]["current"]["temperature_2m"]
    assert blr["reading"]["wind_gust_kmh"] == REAL["bengaluru"]["current"]["wind_gusts_10m"]
    assert blr["data_class"] == "REAL_EXTERNAL" and blr["reading"]["run_id"] == run["id"]
    assert [f["date"] for f in blr["forecast"]] == ["2026-09-27", "2026-09-28", "2026-09-29"]
    assert blr["forecast"][2]["precipitation_mm"] == REAL["bengaluru"]["daily"]["precipitation_sum"][-1]
    for ind in blr["indicators"]:
        assert (ind["basis"], ind["data_class"]) in {("OBSERVED", "REAL_EXTERNAL"), ("FORECAST", "MODEL_PREDICTION")}
        assert ind["rule"]  # every indicator states the rule it applied
    # Historical daily series never includes today's incomplete day or forecasts.
    daily = world["admin"].get("/api/weather/daily", params={"warehouse_id": world["warehouses"]["blr"]["id"],
                                                             "days": 30}).json()
    assert daily["days"][-1]["date"] == "2026-09-26" and len(daily["days"]) == 7


def test_stale_reading_is_flagged_not_hidden(world, http):
    set_coords(world)
    http["handler"] = real_weather
    http["now"] = RECORDED_AT + timedelta(hours=5)
    run = fetch(world["admin"], OPEN_METEO)
    assert run["status"] == "SUCCESS" and run["warnings"] == 2
    assert {i["code"] for i in run["issues"]} == {"STALE_READING"}
    blr = next(w for w in world["admin"].get("/api/weather/current").json() if w["warehouse"]["name"] == "BLR Central")
    assert blr["reading"]["validation_status"] == "ACCEPTED_WITH_WARNING"


def test_future_timestamp_is_rejected(world, http):
    set_coords(world)
    http["handler"] = real_weather
    http["now"] = RECORDED_AT - timedelta(hours=3)
    run = fetch(world["admin"], OPEN_METEO)
    assert run["status"] == "PARTIAL" and {i["code"] for i in run["issues"]} == {"FUTURE_TIMESTAMP"}
    assert run["rows_inserted"] == 14  # the daily rows are still valid


def test_weather_malformed_and_timeout_are_classified(world, http):
    set_coords(world)
    http["handler"] = lambda req: httpx.Response(200, json={"unexpected": True})
    run = fetch(world["admin"], OPEN_METEO)
    assert run["status"] == "FAILED" and run["error_kind"] == "MALFORMED"

    def timeout(req):
        raise httpx.ReadTimeout("timed out", request=req)
    http["handler"] = timeout
    http["calls"].clear()
    run = fetch(world["admin"], OPEN_METEO)
    assert run["status"] == "FAILED" and run["error_kind"] == "TIMEOUT"
    assert len(http["calls"]) == 4  # 2 locations × (1 try + 1 retry)

    http["handler"] = lambda req: httpx.Response(200, text="<html>not json</html>")
    assert fetch(world["admin"], OPEN_METEO)["error_kind"] == "MALFORMED"


def test_failed_refresh_shows_error_with_last_verified_data(world, http):
    set_coords(world)
    http["handler"] = real_weather
    fetch(world["admin"], OPEN_METEO)
    assert source(world["admin"], OPEN_METEO)["status"] == "CONNECTED"

    http["handler"] = lambda req: httpx.Response(503)
    fetch(world["admin"], OPEN_METEO)
    src = source(world["admin"], OPEN_METEO)
    assert src["status"] == "FAILING" and src["last_failure_kind"] == "HTTP"
    assert src["freshness"]["label"] == "ERROR"
    assert "last verified" in src["freshness"]["detail"].lower() and "503" in src["freshness"]["detail"]
    assert src["last_rows_accepted"] == 16  # from the last successful fetch, still shown
    cur = world["admin"].get("/api/weather/current").json()
    assert all(w["freshness"]["label"] == "ERROR" and w["reading"] is not None for w in cur)
    env = {i["key"]: i for i in world["admin"].get("/api/data/environment").json()["items"]}
    assert env["weather"]["status"] == "bad" and "failed" in env["weather"]["summary"]

    # A later success clears the error.
    http["handler"] = real_weather
    fetch(world["admin"], OPEN_METEO)
    assert source(world["admin"], OPEN_METEO)["status"] == "CONNECTED"


def test_weather_filters_respect_scope(world, http):
    set_coords(world)
    http["handler"] = real_weather
    fetch(world["admin"], OPEN_METEO)
    admin, ravi = world["admin"], world["ravi"]
    blr_region = world["regions"]["blr"]["id"]
    assert [w["warehouse"]["name"] for w in admin.get("/api/weather/current", params={"region_id": blr_region}).json()] \
        == ["BLR Central"]
    hyd = world["warehouses"]["hyd"]["id"]
    assert ravi.get("/api/weather/current", params={"warehouse_id": hyd}).status_code == 403
    assert world["other"].get("/api/weather/current", params={"warehouse_id": hyd}).status_code == 404


def test_indicator_rules():
    now = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
    from app.schemas.data import ForecastDay, WeatherReading
    hot = WeatherReading(observed_at=now - timedelta(minutes=20), temperature_c=41.0, humidity_pct=30,
                         precipitation_mm=0, rain_mm=0, wind_kmh=10, wind_gust_kmh=65, weather_code=95,
                         condition=None, fetched_at=now, run_id=None, validation_status="ACCEPTED")
    inds, _ = indicators.evaluate(hot, [{"obs_date": date(2026, 9, 26), "precipitation_mm": 70.0}], [], now)
    keys = {(i.key, i.level) for i in inds}
    assert {("HEAT", "WARNING"), ("WIND", "WARNING"), ("STORM", "WARNING"), ("RAIN", "WARNING")} <= keys
    old = hot.model_copy(update={"observed_at": now - timedelta(hours=7)})
    inds, note = indicators.evaluate(old, [], [], now)
    assert inds == [] and "6 hours" in note
    fc = [ForecastDay(date=date(2026, 9, 27), temp_max_c=30, temp_min_c=20, precipitation_mm=80.0,
                      precipitation_probability=90, wind_max_kmh=10, weather_code=63, condition=None, issued_at=now)]
    inds, _ = indicators.evaluate(None, [], fc, now)
    assert inds[0].basis == "FORECAST" and inds[0].data_class == "MODEL_PREDICTION" and "today" in inds[0].title


# --------------------------------------------------------------------------- mandi prices


def test_mandi_run_is_public_and_shared(world, http, ogd_key):
    http["handler"] = lambda req: httpx.Response(200, json=OGD)
    run = fetch(world["admin"], OGD_MANDI)
    assert run["scope"] == "PUBLIC" and run["endpoint"].endswith(get_settings().ogd_mandi_resource_id)
    assert FAKE_KEY not in json.dumps(run)
    other = world["other"]
    listed = {r["id"]: r for r in other.get("/api/data/runs").json()}
    assert run["id"] in listed and listed[run["id"]]["triggered_by"] == "Another workspace"
    assert other.get(f"/api/data/runs/{run['id']}").status_code == 200
    # Both workspaces see the same source health; a second fetch while one runs is refused for everyone.
    assert source(other, OGD_MANDI)["last_run"]["id"] == run["id"]
    assert FAKE_KEY not in json.dumps(world["admin"].get("/api/data/sources").json())


def test_mandi_duplicates_are_counted_not_inserted(world, http, ogd_key):
    http["handler"] = lambda req: httpx.Response(200, json=OGD)
    fetch(world["admin"], OGD_MANDI)
    second = fetch(world["admin"], OGD_MANDI)
    assert second["rows_inserted"] == 0 and second["rows_duplicate"] == 4
    dup = json.loads(json.dumps(OGD))
    dup["records"].append(dict(dup["records"][0]))
    dup["total"] = dup["count"] = len(dup["records"])
    http["handler"] = lambda req: httpx.Response(200, json=dup)
    third = fetch(world["admin"], OGD_MANDI)
    assert third["rows_duplicate"] == 5 and third["rows_inserted"] == 0


def test_mandi_auth_empty_and_malformed(world, http, ogd_key):
    http["handler"] = lambda req: httpx.Response(401, json={"message": "unauthorised"})
    run = fetch(world["admin"], OGD_MANDI)
    assert run["status"] == "FAILED" and run["error_kind"] == "AUTH"
    src = source(world["admin"], OGD_MANDI)
    assert src["auth_status"] == "REJECTED" and src["status"] == "FAILING"
    assert src["freshness"]["label"] == "UNAVAILABLE"  # never any verified data → not "healthy", not a guess
    latest = world["admin"].get("/api/market/latest").json()
    assert all(r["data_class"] == "UNAVAILABLE" for r in latest)

    http["handler"] = lambda req: httpx.Response(200, json={"total": 0, "count": 0, "records": []})
    run = fetch(world["admin"], OGD_MANDI)
    assert run["status"] == "SUCCESS" and run["rows_received"] == 0 and "no records" in run["params"]["note"]

    http["handler"] = lambda req: httpx.Response(200, json={"status": "ok"})
    run = fetch(world["admin"], OGD_MANDI)
    assert run["status"] == "FAILED" and run["error_kind"] == "MALFORMED"


def test_price_provenance_and_filters(world, http, ogd_key):
    http["handler"] = lambda req: httpx.Response(200, json=OGD)
    run = fetch(world["admin"], OGD_MANDI)
    admin = world["admin"]
    page = admin.get("/api/market/prices", params={"commodity": "Tomato"}).json()
    row = page["rows"][0]
    assert row["data_class"] == "REAL_EXTERNAL" and row["run_id"] == run["id"] and row["unit"] == "INR/quintal"
    detail = admin.get(f"/api/market/prices/{row['id']}").json()
    assert detail["source_dataset"] == get_settings().ogd_mandi_resource_id
    assert detail["source_record_id"] and detail["raw_reference"]["market"] in {"Test Market A", "Test Market B"}
    assert FAKE_KEY not in json.dumps(detail) and "api-key" not in detail["source_endpoint"]
    assert detail["run"]["id"] == run["id"] and detail["publisher"]

    warned = admin.get("/api/market/prices", params={"validation": "ACCEPTED_WITH_WARNING"}).json()
    assert warned["total"] == 1 and warned["rows"][0]["validation_notes"]
    assert admin.get("/api/market/prices", params={"freshness": "DAILY"}).json()["total"] == 4
    assert admin.get("/api/market/prices", params={"freshness": "HISTORICAL"}).json()["total"] == 0
    assert admin.get("/api/market/prices", params={"freshness": "LIVE"}).status_code == 422

    cmp = admin.get("/api/market/compare", params={"commodity": "Tomato", "by": "market"}).json()
    assert [(r["name"], r["modal"]) for r in cmp["rows"]] == [("Test Market B", 1500.0), ("Test Market A", 1300.0)]
    by_district = admin.get("/api/market/compare", params={"commodity": "Onion", "by": "district"}).json()
    assert {r["name"] for r in by_district["rows"]} == {"Mysore", "Kolar"}
    assert admin.get("/api/market/compare", params={"commodity": "Tomato", "by": "planet"}).status_code == 422
    latest = {r["commodity"]: r for r in admin.get("/api/market/latest").json()}
    assert latest["Tomato"]["data_class"] == "REAL_EXTERNAL" and latest["Tomato"]["change_abs"] is None


def test_uploaded_price_detail_is_private(world):
    csv = ("state,district,market,commodity,arrival_date,min_price,max_price,modal_price\n"
           "Karnataka,Bangalore,KR Market,Tomato,2026-09-20,1000,1500,1200\n")
    r = world["admin"].client.post("/api/imports/market-prices?dry_run=false", headers=world["admin"]._h(),
                                   files={"file": ("mine.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    row = world["admin"].get("/api/market/prices").json()["rows"][0]
    assert row["data_class"] == "REAL_ORGANIZATION"
    detail = world["admin"].get(f"/api/market/prices/{row['id']}").json()
    assert detail["source_dataset"] == "Upload: mine.csv" and detail["raw_reference"]["market"] == "KR Market"
    assert world["other"].get(f"/api/market/prices/{row['id']}").status_code == 404


# --------------------------------------------------------------------------- data origin & environment


def test_environment_classifies_synthetic_mixed_and_real(world, db):
    env = {i["key"]: i for i in world["admin"].get("/api/data/environment").json()["items"]}
    assert env["inventory"]["data_class"] == "REAL_ORGANIZATION"  # created through the API by a user
    assert env["market_prices"]["data_class"] == "UNAVAILABLE"
    assert env["weather"]["data_class"] == "UNAVAILABLE"
    assert env["demand_history"]["data_class"] == "UNAVAILABLE"
    assert env["predictions"]["summary"] == "None"

    org_id = world["admin"].me["organization"]["id"]
    for item in db.scalars(select(InventoryItem)).all():
        if str(item.organization_id) == org_id:
            item.data_origin = DataOrigin.SYNTHETIC_DEMO
    db.commit()
    env = {i["key"]: i for i in world["admin"].get("/api/data/environment").json()["items"]}
    assert env["inventory"]["data_class"] == "SYNTHETIC_DEMO" and env["inventory"]["status"] == "warn"
    items = world["admin"].get("/api/inventory").json()
    assert all(i["data_class"] == "SYNTHETIC_DEMO" for i in items)

    # A manual edit turns that record into organization data → the section becomes MIXED.
    blr = world["inventory"]["blr"]["id"]
    assert world["admin"].patch(f"/api/inventory/{blr}", {"quantity": 125}).status_code == 200
    got = world["admin"].get(f"/api/inventory/{blr}").json()
    assert got["data_origin"] == "MANUAL_ENTRY" and got["data_class"] == "REAL_ORGANIZATION"
    env = {i["key"]: i for i in world["admin"].get("/api/data/environment").json()["items"]}
    assert env["inventory"]["data_class"] == "MIXED"
    # Another organization's classification is unaffected.
    other = {i["key"]: i for i in world["other"].get("/api/data/environment").json()["items"]}
    assert other["inventory"]["data_class"] == "REAL_ORGANIZATION"


def test_csv_import_sets_origin(world):
    ravi = world["ravi"]
    csv = "warehouse,commodity,quantity\nBLR Central,Rice,50\n"
    r = ravi.client.post("/api/imports/inventory?dry_run=false", headers=ravi._h(),
                         files={"file": ("s.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    rice = next(i for i in ravi.get("/api/inventory").json() if i["commodity"]["name"] == "Rice")
    assert rice["data_origin"] == "CSV_IMPORT" and rice["data_class"] == "REAL_ORGANIZATION"
    moves = ravi.get("/api/inventory/movements").json()
    assert moves[0]["data_origin"] == "CSV_IMPORT"


def test_dashboard_carries_environment_and_region_filter(world):
    dash = world["ops"].get("/api/dashboard").json()
    assert {i["key"] for i in dash["environment"]["items"]} >= {"market_prices", "weather", "inventory"}
    blr = world["regions"]["blr"]["id"]
    filtered = world["ops"].get("/api/dashboard", params={"region_id": blr}).json()
    assert [w["name"] for w in filtered["warehouses"]] == ["BLR Central"] and filtered["region_filter"] == "Bengaluru"
    assert world["other"].get("/api/dashboard", params={"region_id": blr}).status_code == 404
    # A scoped user filtering to a region outside their scope sees nothing, not the other region's data.
    hyd = world["regions"]["hyd"]["id"]
    assert world["ravi"].get("/api/dashboard", params={"region_id": hyd}).json()["warehouses"] == []


# --------------------------------------------------------------------------- source settings


def test_auto_refresh_setting_is_per_organization(world):
    admin, other = world["admin"], world["other"]
    url = f"/api/data/sources/{OPEN_METEO}/settings"
    assert admin.get(url).json() == {"auto_refresh": True}
    assert world["viewer"].patch(url, {"auto_refresh": False}).status_code == 403
    assert world["analyst"].patch(url, {"auto_refresh": False}).status_code == 403
    assert admin.patch(url, {"auto_refresh": False}).json() == {"auto_refresh": False}
    assert admin.get(url).json() == {"auto_refresh": False} and other.get(url).json() == {"auto_refresh": True}
    assert source(admin, OPEN_METEO)["auto_refresh"] is False
    assert admin.patch("/api/data/sources/csv_market_prices/settings", {"auto_refresh": False}).status_code == 400
    assert admin.patch("/api/data/sources/nope/settings", {"auto_refresh": False}).status_code == 404
    logs = admin.get("/api/audit-logs").json()
    rows = logs["items"] if isinstance(logs, dict) else logs
    assert any(r["action"] == "data.source_settings" for r in rows)


# --------------------------------------------------------------------------- scheduler


def _now_ist(h, m):
    return datetime(2026, 9, 27, h, m, tzinfo=freshness.IST).astimezone(UTC)


def test_scheduler_plans_weather_per_org_and_respects_settings(world, http, db):
    set_coords(world)
    now = _now_ist(11, 0)
    org_a = world["admin"].me["organization"]["id"]
    jobs = sched.plan(db, now)
    assert [(j.source_key, str(j.organization_id)) for j in jobs] == [(OPEN_METEO, org_a)]  # org B has no coordinates

    world["admin"].patch(f"/api/data/sources/{OPEN_METEO}/settings", {"auto_refresh": False})
    db.expire_all()
    assert sched.plan(db, now) == []
    world["admin"].patch(f"/api/data/sources/{OPEN_METEO}/settings", {"auto_refresh": True})
    db.expire_all()

    src = get_source(db, OPEN_METEO)
    run = IngestionRun(source_id=src.id, organization_id=world_org(db, org_a), trigger=RunTrigger.SCHEDULED,
                       status=RunStatus.SUCCESS, started_at=now, finished_at=now, params={})
    db.add(run)
    db.commit()
    assert sched.plan(db, now + timedelta(minutes=30)) == []
    assert len(sched.plan(db, now + timedelta(minutes=61))) == 1
    run.status = RunStatus.FAILED
    db.commit()
    assert sched.plan(db, now + timedelta(minutes=10)) == []
    assert len(sched.plan(db, now + timedelta(minutes=21))) == 1  # retry after failure, not in a tight loop


def world_org(db, org_id):
    import uuid
    return uuid.UUID(org_id)


def test_scheduler_market_slots(world, db):
    s = get_settings()
    assert sched.plan(db, _now_ist(11, 0)) == []  # no API key → never scheduled
    s.data_gov_in_api_key = FAKE_KEY
    try:
        assert [j.organization_id for j in sched.plan(db, _now_ist(11, 0))] == [None]  # 10:30 slot passed
        src = get_source(db, OGD_MANDI)
        db.add(IngestionRun(source_id=src.id, organization_id=None, trigger=RunTrigger.SCHEDULED,
                            status=RunStatus.SUCCESS, started_at=_now_ist(10, 31), finished_at=_now_ist(10, 32)))
        db.commit()
        assert sched.plan(db, _now_ist(14, 0)) == []
        assert len(sched.plan(db, _now_ist(14, 31))) == 1
        assert sched.next_market_at(db.scalars(select(IngestionRun)).first(), _now_ist(11, 0)) == _now_ist(14, 30)
    finally:
        s.data_gov_in_api_key = ""


def test_run_due_executes_and_writes_heartbeat(world, http, db):
    from tests.conftest import TestingSession
    set_coords(world)
    http["handler"] = real_weather
    assert sched.scheduler_status(db)[0] is False
    ids = sched.run_due(TestingSession, _now_ist(11, 0))
    assert len(ids) == 1
    db.expire_all()
    run = db.get(IngestionRun, ids[0])
    assert run.status == RunStatus.SUCCESS and run.trigger == RunTrigger.SCHEDULED
    running, beat = sched.scheduler_status(db)
    assert running and beat is not None
    src = source(world["admin"], OPEN_METEO)
    assert src["scheduler_running"] is True and src["next_scheduled_at"] is not None
    # Nothing is due again straight away: restarts never double-fetch.
    assert sched.run_due(TestingSession, _now_ist(11, 1)) == []


def test_no_synthetic_fallback_when_sources_fail(world, http, ogd_key, db):
    """A failing source must never produce market or weather rows."""
    set_coords(world)
    http["handler"] = lambda req: httpx.Response(500)
    fetch(world["admin"], OPEN_METEO)
    fetch(world["admin"], OGD_MANDI)
    assert db.scalar(select(MarketPrice.id).limit(1)) is None
    assert db.scalar(select(WeatherObservation.id).limit(1)) is None
    assert db.scalar(select(Warehouse.id).where(Warehouse.data_origin == DataOrigin.SYNTHETIC_DEMO).limit(1)) is None
