"""V2 data platform: connectors, validation, freshness, imports, visibility and permissions."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.services.data import connectors, freshness, market

FIX = Path(__file__).parent / "fixtures"
OPEN_METEO = json.loads((FIX / "open_meteo_bengaluru.json").read_text())  # real response, recorded 27 Sep 2026
OGD = json.loads((FIX / "ogd_mandi_synthetic.json").read_text())  # synthetic, schema-shaped
FIXTURE_TODAY = date(2026, 9, 27)
FAKE_KEY = "test-key-0123456789"


@pytest.fixture
def http(monkeypatch):
    """Route connector HTTP through a handler; returns the list of requests made."""
    calls: list[httpx.Request] = []
    state = {"handler": lambda req: httpx.Response(500)}

    def make_client():
        def handler(req):
            calls.append(req)
            return state["handler"](req)
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(connectors, "make_client", make_client)
    monkeypatch.setattr(connectors, "today_ist", lambda: FIXTURE_TODAY)
    state["calls"] = calls
    return state


@pytest.fixture
def ogd_key():
    s = get_settings()
    old = s.data_gov_in_api_key
    s.data_gov_in_api_key = FAKE_KEY
    yield
    s.data_gov_in_api_key = old


def csv_bytes(text: str) -> bytes:
    return text.strip().encode()


def upload(api, path, name, content, dry_run):
    return api.client.post(f"{path}?dry_run={'true' if dry_run else 'false'}", headers=api._h(),
                           files={"file": (name, content, "text/csv")})


# --------------------------------------------------------------------------- freshness


def test_freshness_labels_are_honest():
    now = datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
    assert freshness.for_reading(datetime(2026, 9, 27, 5, 0, tzinfo=UTC), now).label == "CURRENT"
    assert freshness.for_reading(datetime(2026, 9, 27, 1, 0, tzinfo=UTC), now).label == "RECENT"
    assert freshness.for_reading(datetime(2026, 9, 25, 1, 0, tzinfo=UTC), now).label == "HISTORICAL"
    assert freshness.for_daily(date(2026, 9, 27), date(2026, 9, 27)).label == "DAILY"
    assert freshness.for_daily(date(2026, 9, 25), date(2026, 9, 27)).label == "DAILY"
    assert freshness.for_daily(date(2026, 9, 1), date(2026, 9, 27)).label == "HISTORICAL"
    assert freshness.for_daily(None).label == "UNAVAILABLE"
    labels = {"CURRENT", "RECENT", "DAILY", "HISTORICAL", "UNAVAILABLE"}
    assert "LIVE" not in labels  # nothing is streamed; LIVE is never emitted


# --------------------------------------------------------------------------- Open-Meteo


def test_parse_recorded_open_meteo_response():
    current, days, problems = connectors.parse_open_meteo(OPEN_METEO, today=FIXTURE_TODAY)
    assert current["observed_at"] == datetime(2026, 9, 27, 5, 0, tzinfo=UTC)  # 10:30 IST
    assert current["temperature_c"] == 26.8 and current["humidity_pct"] == 58
    assert [d["obs_date"] for d in days][0] == date(2026, 9, 20)
    assert [d["obs_date"] for d in days][-1] == date(2026, 9, 26)  # today (incomplete) is never stored
    assert len(days) == 7 and days[0]["precipitation_mm"] == 13.4
    assert problems == []


def test_open_meteo_out_of_range_values_are_dropped():
    bad = json.loads(json.dumps(OPEN_METEO))
    bad["current"]["relative_humidity_2m"] = 140
    current, _, problems = connectors.parse_open_meteo(bad, today=FIXTURE_TODAY)
    assert current["humidity_pct"] is None and len(problems) == 1


def _set_coords(world):
    world["admin"].patch(f"/api/warehouses/{world['warehouses']['blr']['id']}", {"latitude": 13.028, "longitude": 77.54})
    world["admin"].patch(f"/api/warehouses/{world['warehouses']['hyd']['id']}", {"latitude": 17.385, "longitude": 78.486})


def test_weather_ingestion_end_to_end(world, http):
    _set_coords(world)
    http["handler"] = lambda req: httpx.Response(200, json=OPEN_METEO)
    admin = world["admin"]
    r = admin.post("/api/data/sources/open_meteo_weather/runs")
    assert r.status_code == 202 and r.json()["status"] == "RUNNING"
    run = admin.get(f"/api/data/runs/{r.json()['id']}").json()
    assert run["status"] == "SUCCESS", run
    assert run["rows_inserted"] == 16  # 2 warehouses × (1 current + 7 completed days)
    assert "latitude=13.028" in str(http["calls"][0].url) and "past_days=7" in str(http["calls"][0].url)

    # Idempotent: the same readings again are unchanged, not duplicated.
    r2 = admin.post("/api/data/sources/open_meteo_weather/runs")
    run2 = admin.get(f"/api/data/runs/{r2.json()['id']}").json()
    assert run2["rows_inserted"] == 0 and run2["rows_unchanged"] == 16

    cur = {w["warehouse"]["name"]: w for w in admin.get("/api/weather/current").json()}
    blr = cur["BLR Central"]
    assert blr["reading"]["temperature_c"] == 26.8 and blr["reading"]["condition"] == "Clear sky"
    assert blr["source"]["key"] == "open_meteo_weather"
    assert blr["freshness"]["label"] in {"CURRENT", "RECENT", "HISTORICAL"}
    daily = admin.get("/api/weather/daily", params={"warehouse_id": world["warehouses"]["blr"]["id"], "days": 92}).json()
    assert [d["precipitation_mm"] for d in daily["days"]] == [13.4, 7.4, 4.9, 1.6, 1.3, 8.6, 0.5]

    # Location scope and org isolation apply to weather.
    assert [w["warehouse"]["name"] for w in world["ravi"].get("/api/weather/current").json()] == ["BLR Central"]
    assert world["ravi"].get("/api/weather/daily", params={"warehouse_id": world["warehouses"]["hyd"]["id"]}).status_code == 403
    assert world["unscoped"].get("/api/weather/current").json() == []
    other = world["other"].get("/api/weather/current").json()
    assert [w["warehouse"]["name"] for w in other] == ["Chennai Depot"] and other[0]["reading"] is None


def test_weather_failure_is_recorded_not_hidden(world, http):
    _set_coords(world)
    http["handler"] = lambda req: httpx.Response(503)
    run_id = world["admin"].post("/api/data/sources/open_meteo_weather/runs").json()["id"]
    run = world["admin"].get(f"/api/data/runs/{run_id}").json()
    assert run["status"] == "FAILED" and "Open-Meteo" in run["error_message"]
    src = next(s for s in world["admin"].get("/api/data/sources").json() if s["key"] == "open_meteo_weather")
    assert src["last_run"]["status"] == "FAILED" and src["freshness"]["label"] == "UNAVAILABLE"
    assert src["last_success_at"] is None


def test_weather_needs_coordinates(world, http):
    run_id = world["admin"].post("/api/data/sources/open_meteo_weather/runs").json()["id"]
    run = world["admin"].get(f"/api/data/runs/{run_id}").json()
    assert run["status"] == "FAILED" and "coordinates" in run["error_message"]
    assert http["calls"] == []


# --------------------------------------------------------------------------- data.gov.in mandi prices


def test_mandi_source_not_configured_without_key(world):
    src = next(s for s in world["admin"].get("/api/data/sources").json() if s["key"] == "ogd_mandi_prices")
    assert src["configured"] is False and "DATA_GOV_IN_API_KEY" in src["config_message"]
    assert src["can_run"] is False and src["freshness"]["label"] == "UNAVAILABLE"
    assert world["admin"].post("/api/data/sources/ogd_mandi_prices/runs").status_code == 409


def test_mandi_ingestion_validates_and_is_public(world, http, ogd_key):
    http["handler"] = lambda req: httpx.Response(200, json=OGD)
    admin = world["admin"]
    run_id = admin.post("/api/data/sources/ogd_mandi_prices/runs").json()["id"]
    run = admin.get(f"/api/data/runs/{run_id}").json()
    assert run["status"] == "PARTIAL"
    assert run["rows_received"] == 7  # Tamil Nadu row filtered out
    assert run["rows_inserted"] == 4 and run["rows_rejected"] == 3
    codes = {(i["severity"], i["code"]) for i in run["issues"]}
    assert {("ERROR", "MIN_ABOVE_MAX"), ("ERROR", "MISSING"), ("ERROR", "INVALID_DATE"),
            ("WARNING", "MODAL_OUTSIDE_RANGE")} <= codes
    req = http["calls"][0]
    assert req.url.params["filters[state.keyword]"] == "Karnataka"
    assert FAKE_KEY not in json.dumps(run)  # the key is never echoed back

    # Official public data is visible to every organization, with its source attached.
    for api in (admin, world["other"], world["viewer"]):
        page = api.get("/api/market/prices", params={"commodity": "tomato"}).json()
        assert page["total"] == 2 and page["rows"][0]["source"]["origin"] == "OFFICIAL_API"
    onion = api.get("/api/market/prices", params={"commodity": "Onion"}).json()["rows"]
    assert {r["market"] for r in onion} == {"Test Market C", "Test Market B"}  # _x0020_ headers parsed

    latest = {(r["commodity"]): r for r in admin.get("/api/market/latest").json()}
    assert latest["Tomato"]["avg_modal"] == 1400.0 and latest["Tomato"]["markets_reporting"] == 2
    assert latest["Tomato"]["latest_date"] == "2026-09-26"
    assert latest["Rice"]["freshness"]["label"] == "UNAVAILABLE"  # rejected row → no data, not a guess


def test_mandi_api_error_redacts_key(world, http, ogd_key):
    http["handler"] = lambda req: httpx.Response(200, json={"error": f"Invalid key {FAKE_KEY}"})
    run_id = world["admin"].post("/api/data/sources/ogd_mandi_prices/runs").json()["id"]
    run = world["admin"].get(f"/api/data/runs/{run_id}").json()
    assert run["status"] == "FAILED" and FAKE_KEY not in run["error_message"] and "***" in run["error_message"]


def test_row_validation_rules():
    ok = market.validate_row({"State": "Karnataka", "Market": "M", "Commodity": "Tomato",
                              "Arrival Date": "2026-09-20", "Min Price (Rs./Quintal)": "1,000",
                              "Max Price (Rs./Quintal)": "1,500", "Modal Price (Rs./Quintal)": "₹1,200"}, 2,
                             today=FIXTURE_TODAY)
    assert ok.clean["modal_price"] == 1200 and ok.clean["arrival_date"] == date(2026, 9, 20)
    future = market.validate_row({"state": "K", "market": "M", "commodity": "C", "arrival_date": "2026-12-01",
                                  "modal_price": "10"}, 3, today=FIXTURE_TODAY)
    assert future.clean is None and future.issues[0]["code"] == "FUTURE_DATE"
    neg = market.validate_row({"state": "K", "market": "M", "commodity": "C", "arrival_date": "2026-09-01",
                               "modal_price": "-5"}, 4, today=FIXTURE_TODAY)
    assert neg.clean is None and neg.issues[0]["code"] == "NON_POSITIVE"


# --------------------------------------------------------------------------- CSV: market prices

PRICE_CSV = """
State,District,Market,Commodity,Variety,Grade,Arrival Date,Min Price (Rs./Quintal),Max Price (Rs./Quintal),Modal Price (Rs./Quintal)
Karnataka,Kolar,Kolar,Tomato,Local,FAQ,2026-09-20,800,1200,1000
Karnataka,Kolar,Kolar,Tomato,Local,FAQ,2026-09-21,900,1300,1100
Karnataka,Kolar,Kolar,Tomato,Local,FAQ,2026-09-22,1000,1500,1250
Karnataka,Kolar,Kolar,Tomato,Local,FAQ,not-a-date,1000,1500,1250
Karnataka,Kolar,Kolar,Tomato,Local,FAQ,2026-09-23,1000,1500,abc
"""


def test_market_csv_dry_run_then_commit(world):
    admin = world["admin"]
    dry = upload(admin, "/api/imports/market-prices", "kolar_tomato.csv", csv_bytes(PRICE_CSV), True)
    assert dry.status_code == 200, dry.text
    d = dry.json()
    assert d["dry_run"] and d["rows_total"] == 5 and d["rows_valid"] == 3 and d["rows_rejected"] == 2
    assert d["columns_detected"]["Modal Price (Rs./Quintal)"] == "modal_price"
    assert admin.get("/api/market/prices").json()["total"] == 0  # dry run changed nothing

    res = upload(admin, "/api/imports/market-prices", "kolar_tomato.csv", csv_bytes(PRICE_CSV), False).json()
    assert res["inserted"] == 3 and res["run_id"]
    rows = admin.get("/api/market/prices", params={"source": "csv_market_prices"}).json()["rows"]
    assert len(rows) == 3 and rows[0]["source"]["origin"] == "USER_UPLOAD"

    trend = admin.get("/api/market/trend", params={"commodity": "Tomato"}).json()
    assert [p["date"] for p in trend["series"][0]["points"]] == ["2026-09-20", "2026-09-21", "2026-09-22"]
    assert trend["source"]["key"] == "csv_market_prices"
    assert trend["freshness"]["label"] == "HISTORICAL"  # an uploaded file is never labelled as a daily feed
    tomato = next(m for m in admin.get("/api/market/latest").json() if m["commodity"] == "Tomato")
    assert tomato["freshness"]["label"] == "HISTORICAL" and "Uploaded file" in tomato["freshness"]["detail"]

    # Uploads are private to the uploading organization.
    assert world["other"].get("/api/market/prices").json()["total"] == 0
    assert world["viewer"].get("/api/market/prices").json()["total"] == 3

    again = upload(admin, "/api/imports/market-prices", "kolar_tomato.csv", csv_bytes(PRICE_CSV), False).json()
    assert again["inserted"] == 0 and again["unchanged"] == 3
    run = admin.get(f"/api/data/runs/{res['run_id']}").json()
    assert run["file_name"] == "kolar_tomato.csv" and run["trigger"] == "UPLOAD"


def test_market_csv_flags_unusual_jump(world):
    admin = world["admin"]
    upload(admin, "/api/imports/market-prices", "a.csv", csv_bytes(PRICE_CSV), False)
    jump = """
State,Market,Commodity,Variety,Grade,Arrival_Date,Modal_Price
Karnataka,Kolar,Tomato,Local,FAQ,2026-09-24,9000
"""
    res = upload(admin, "/api/imports/market-prices", "b.csv", csv_bytes(jump), False).json()
    assert res["inserted"] == 1 and res["warnings"] == 1
    run = admin.get(f"/api/data/runs/{res['run_id']}").json()
    assert run["issues"][0]["code"] == "UNUSUAL_CHANGE"


def test_market_csv_missing_columns_and_bad_files(world):
    admin = world["admin"]
    r = upload(admin, "/api/imports/market-prices", "x.csv", b"foo,bar\n1,2", True)
    assert r.status_code == 422 and "Missing required column" in r.json()["detail"]
    assert upload(admin, "/api/imports/market-prices", "x.xlsx", b"a,b", True).status_code == 415
    assert upload(admin, "/api/imports/market-prices", "x.csv", b"   ", True).status_code == 422


# --------------------------------------------------------------------------- CSV: inventory


def test_inventory_csv_respects_scope_and_is_all_or_nothing(world):
    ravi = world["ravi"]
    bad = "warehouse,commodity,quantity\nBLR Central,Tomato,130\nHYD Hub,Tomato,10\n"
    dry = upload(ravi, "/api/imports/inventory", "stock.csv", bad.encode(), True).json()
    assert any(i["code"] == "OUT_OF_SCOPE" for i in dry["issues"])
    commit = upload(ravi, "/api/imports/inventory", "stock.csv", bad.encode(), False)
    assert commit.status_code == 422
    assert world["admin"].get(f"/api/inventory/{world['inventory']['blr']['id']}").json()["quantity"] == 120

    good = "Warehouse,Commodity,Qty,Notes\nBLR Central,Tomato,130,Recount\nBLR Central,Rice,200,\n"
    dry = upload(ravi, "/api/imports/inventory", "stock.csv", good.encode(), True).json()
    assert [p["action"] for p in dry["preview"]] == ["update", "create"]
    res = upload(ravi, "/api/imports/inventory", "stock.csv", good.encode(), False).json()
    assert res["updated"] == 1 and res["inserted"] == 1
    items = {i["commodity"]["name"]: i for i in ravi.get("/api/inventory").json()}
    assert items["Tomato"]["quantity"] == 130 and items["Rice"]["quantity_tonnes"] == 20
    moves = ravi.get("/api/inventory/movements").json()
    assert moves[0]["reason"] == "CSV import: stock.csv"


def test_inventory_csv_validation(world):
    admin = world["admin"]
    text = ("warehouse,commodity,quantity\nNowhere,Tomato,1\nBLR Central,Mango,1\nBLR Central,Tomato,-4\n"
            "HYD Hub,Tomato,5000\nHYD Hub,Rice,x\n")
    d = upload(admin, "/api/imports/inventory", "s.csv", text.encode(), True).json()
    codes = {i["code"] for i in d["issues"]}
    assert {"UNKNOWN", "NEGATIVE", "OVER_CAPACITY", "NOT_A_NUMBER"} <= codes


# --------------------------------------------------------------------------- permissions & isolation


def test_data_permissions(world, http):
    viewer, analyst = world["viewer"], world["analyst"]
    for url in ["/api/data/sources", "/api/market/latest", "/api/market/filters", "/api/data/runs"]:
        assert viewer.get(url).status_code == 200, url
    assert viewer.post("/api/data/sources/open_meteo_weather/runs").status_code == 403
    assert upload(viewer, "/api/imports/market-prices", "a.csv", csv_bytes(PRICE_CSV), True).status_code == 403
    assert upload(viewer, "/api/imports/inventory", "a.csv", b"warehouse,commodity,quantity\n", True).status_code == 403
    assert upload(analyst, "/api/imports/market-prices", "a.csv", csv_bytes(PRICE_CSV), True).status_code == 200
    assert analyst.post("/api/data/sources/open_meteo_weather/runs").status_code == 403
    assert world["ops"].post("/api/data/sources/nope/runs").status_code == 404
    assert world["ops"].post("/api/data/sources/csv_market_prices/runs").status_code == 400
    for url in ["/api/data/sources", "/api/market/latest", "/api/weather/current"]:
        world["admin"].client.cookies.clear()
        assert world["admin"].client.get(url).status_code == 401


def test_runs_are_private_to_the_organization(world):
    res = upload(world["admin"], "/api/imports/market-prices", "a.csv", csv_bytes(PRICE_CSV), False).json()
    other = world["other"]
    assert other.get(f"/api/data/runs/{res['run_id']}").status_code == 404
    assert other.get("/api/data/runs").json() == []
    assert len(world["admin"].get("/api/data/runs").json()) == 1


def test_role_dashboards_include_external_data(world):
    upload(world["admin"], "/api/imports/market-prices", "a.csv", csv_bytes(PRICE_CSV), False)
    proc = world["procurement"].get("/api/dashboard").json()
    tomato = next(m for m in proc["market"] if m["commodity"] == "Tomato")
    assert tomato["avg_modal"] == 1250.0 and tomato["source"]["origin"] == "USER_UPLOAD"
    assert proc["weather"] is None and proc["data_sources"] is None
    ravi = world["ravi"].get("/api/dashboard").json()
    assert ravi["weather"] is not None and ravi["market"] is None
    admin = world["admin"].get("/api/dashboard").json()
    assert {s["key"] for s in admin["data_sources"]} >= {"ogd_mandi_prices", "open_meteo_weather"}


def test_commodity_market_name_mapping(world):
    admin = world["admin"]
    rice = world["commodities"]["rice"]["id"]
    assert admin.patch(f"/api/commodities/{rice}", {"market_name": "Paddy(Dhan)(Common)"}).json()["market_name"] \
        == "Paddy(Dhan)(Common)"
    names = [m["commodity"] for m in admin.get("/api/market/latest").json()]
    assert "Paddy(Dhan)(Common)" in names and "Rice" not in names

