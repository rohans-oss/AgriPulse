"""Connectors that fetch real public data, and the executor that records each run.

HTTP goes through ``make_client`` so tests can swap in recorded responses.
No connector ever substitutes, interpolates or invents values: a failure is recorded
on the run with a classified ``error_kind`` and the UI shows it.
"""

import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Commodity, IngestionIssue, IngestionRun, Warehouse, WeatherObservation
from app.models.enums import IssueSeverity, RecordStatus, RunStatus, ValidationStatus, WeatherKind
from app.services.data import market
from app.services.data.freshness import IST, today_ist
from app.services.data.sources import OGD_MANDI, OPEN_METEO

log = logging.getLogger(__name__)

MAX_OGD_PAGES = 20
OGD_PAGE_SIZE = 1000

OPEN_METEO_CURRENT = "temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m,wind_gusts_10m,weather_code"
OPEN_METEO_DAILY = ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum,"
                    "precipitation_probability_max,wind_speed_10m_max")


class ConnectorError(Exception):
    """A failure whose message is safe to show to users. ``kind`` classifies it."""

    def __init__(self, message: str, kind: str = "UNEXPECTED"):
        super().__init__(message)
        self.kind = kind


def utcnow() -> datetime:
    """Fetch time (a function so tests can pin it to a recorded response's time)."""
    return datetime.now(UTC)


def make_client() -> httpx.Client:
    return httpx.Client(timeout=get_settings().http_timeout_seconds, headers={"User-Agent": "AgriFlowAI/3.0"})


def _redact(text: str) -> str:
    key = get_settings().data_gov_in_api_key
    return text.replace(key, "***") if key else text


def is_configured(source_key: str) -> tuple[bool, str | None]:
    if source_key == OGD_MANDI and not get_settings().data_gov_in_api_key:
        return False, "Set DATA_GOV_IN_API_KEY (free from data.gov.in) to enable this source"
    return True, None


def endpoint_for(source_key: str) -> str:
    s = get_settings()
    if source_key == OGD_MANDI:
        return f"{s.ogd_api_base}/{s.ogd_mandi_resource_id}"
    if source_key == OPEN_METEO:
        return s.open_meteo_base
    return "upload"


def get_json(client: httpx.Client, url: str, params: dict, label: str) -> dict:
    """GET JSON with one retry on timeouts, network errors and 5xx. Raises classified ConnectorError."""
    settings = get_settings()
    attempts = 1 + max(settings.http_retries, 0)
    last: ConnectorError | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(settings.http_backoff_seconds * attempt)
        try:
            resp = client.get(url, params=params)
        except httpx.TimeoutException:
            last = ConnectorError(f"{label} did not respond within {settings.http_timeout_seconds:.0f}s", "TIMEOUT")
            continue
        except httpx.HTTPError as e:
            last = ConnectorError(f"Could not reach {label}: {type(e).__name__}", "NETWORK")
            continue
        if resp.status_code in (401, 403):
            raise ConnectorError(f"{label} rejected the credentials (HTTP {resp.status_code})", "AUTH")
        if resp.status_code == 429:
            raise ConnectorError(f"{label} rate limit reached (HTTP 429); will retry on the next schedule", "RATE_LIMITED")
        if resp.status_code >= 500:
            last = ConnectorError(f"{label} returned HTTP {resp.status_code}", "HTTP")
            continue
        if resp.status_code >= 400:
            raise ConnectorError(f"{label} returned HTTP {resp.status_code}", "HTTP")
        try:
            payload = resp.json()
        except ValueError:
            raise ConnectorError(f"{label} returned a response that is not JSON", "MALFORMED") from None
        if not isinstance(payload, dict):
            raise ConnectorError(f"{label} returned an unexpected JSON structure", "MALFORMED")
        return payload
    assert last is not None
    raise last


# --------------------------------------------------------------------------- data.gov.in mandi prices


def fetch_ogd_mandi(db: Session, run: IngestionRun, client: httpx.Client) -> None:
    settings = get_settings()
    if not settings.data_gov_in_api_key:
        raise ConnectorError("DATA_GOV_IN_API_KEY is not configured", "CONFIG")
    url = endpoint_for(OGD_MANDI)
    run.endpoint = url
    fetched_at = utcnow()
    states = run.params.get("states") or settings.mandi_states
    wanted = {s.strip().lower() for s in states}
    accepted: list[market.Accepted] = []
    issues: list[dict] = []
    row_no = 0
    total_reported = 0

    for state in states:
        offset = 0
        for _ in range(MAX_OGD_PAGES):
            params = {"api-key": settings.data_gov_in_api_key, "format": "json", "limit": OGD_PAGE_SIZE,
                      "offset": offset, "filters[state.keyword]": state}
            try:
                payload = get_json(client, url, params, "data.gov.in")
            except ConnectorError as e:
                raise ConnectorError(_redact(str(e)), e.kind) from None
            if payload.get("error"):
                msg = _redact(str(payload["error"]))[:200]
                kind = "AUTH" if any(w in msg.lower() for w in ("key", "authoriz", "forbidden")) else "HTTP"
                raise ConnectorError(f"data.gov.in error: {msg}", kind)
            if "records" not in payload or not isinstance(payload["records"], list):
                raise ConnectorError("data.gov.in response has no 'records' list", "MALFORMED")
            records = payload["records"]
            try:
                total = int(payload.get("total") or 0)
            except (TypeError, ValueError):
                raise ConnectorError("data.gov.in response has an invalid 'total'", "MALFORMED") from None
            total_reported += total if offset == 0 else 0
            for rec in records:
                if not isinstance(rec, dict):
                    raise ConnectorError("data.gov.in returned a record that is not an object", "MALFORMED")
                row_no += 1
                # Guard in case the server ignored the state filter.
                rstate = str(rec.get("state") or rec.get("State") or "").strip().lower()
                if rstate and rstate not in wanted:
                    continue
                run.rows_received += 1
                res = market.validate_row(rec, row_no, stale_days=market.STALE_DAYS)
                issues += res.issues
                if res.clean:
                    accepted.append(market.Accepted(row_no, res.clean, dict(rec), market.record_id(rec),
                                                    market.warnings_for(res.issues, row_no)))
            offset += len(records)
            if not records or offset >= total:
                break

    run.params = {**run.params, "states": list(states), "resource_id": settings.ogd_mandi_resource_id,
                  "records_reported_by_source": total_reported}
    if run.rows_received == 0:
        run.params["note"] = "The source returned no records for the requested states"
    _finish_market(db, run, accepted, issues, None, fetched_at, dataset=settings.ogd_mandi_resource_id, endpoint=url)


def _finish_market(db, run, accepted, issues, org_id, fetched_at, *, dataset, endpoint):
    market.record_issues(db, run, issues)
    run.rows_rejected = sum(1 for i in issues if i["severity"] == IssueSeverity.ERROR)
    stats = market.upsert_prices(db, run, accepted, org_id, fetched_at, dataset=dataset, endpoint=endpoint)
    run.rows_inserted, run.rows_updated, run.rows_unchanged = stats.inserted, stats.updated, stats.unchanged
    run.rows_duplicate = stats.unchanged + stats.duplicate_in_batch
    run.warnings = stats.warnings + sum(1 for i in issues if i["severity"] == IssueSeverity.WARNING)


# --------------------------------------------------------------------------- Open-Meteo weather


def _key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _in_range(v, lo, hi) -> bool:
    return v is None or lo <= v <= hi


RANGES = {"temperature_c": (-40, 60), "humidity_pct": (0, 100), "precipitation_mm": (0, 1000), "rain_mm": (0, 1000),
          "wind_kmh": (0, 400), "wind_gust_kmh": (0, 500), "wind_max_kmh": (0, 400), "temp_max_c": (-40, 60),
          "temp_min_c": (-40, 60), "precipitation_probability": (0, 100)}


def _daily(daily: dict, key: str, i: int):
    values = daily.get(key)
    return values[i] if isinstance(values, list) and i < len(values) else None


def _check_ranges(rec: dict, problems: list[str]) -> None:
    for f, (lo, hi) in RANGES.items():
        if f in rec and not _in_range(rec[f], lo, hi):
            problems.append(f"{f}={rec[f]} outside plausible range {lo}..{hi}")
            rec[f] = None


def parse_open_meteo(payload: dict, today: date | None = None) -> tuple[dict | None, list[dict], list[str]]:
    """Return (current, completed_days, problems). Today and future days are forecasts — see parse_forecast."""
    today = today or today_ist()
    problems: list[str] = []
    current = None
    cur = payload.get("current") or {}
    if cur.get("time") is not None:
        current = {
            "observed_at": datetime.fromtimestamp(int(cur["time"]), UTC),
            "temperature_c": cur.get("temperature_2m"),
            "humidity_pct": cur.get("relative_humidity_2m"),
            "precipitation_mm": cur.get("precipitation"),
            "rain_mm": cur.get("rain"),
            "wind_kmh": cur.get("wind_speed_10m"),
            "wind_gust_kmh": cur.get("wind_gusts_10m"),
            "weather_code": cur.get("weather_code"),
        }
    days = []
    daily = payload.get("daily") or {}
    for i, t in enumerate(daily.get("time") or []):
        start = datetime.fromtimestamp(int(t), IST)
        if start.date() >= today:  # today is incomplete, later days are forecasts
            continue
        days.append({
            "observed_at": start.astimezone(UTC), "obs_date": start.date(),
            "temp_max_c": _daily(daily, "temperature_2m_max", i), "temp_min_c": _daily(daily, "temperature_2m_min", i),
            "precipitation_mm": _daily(daily, "precipitation_sum", i), "rain_mm": _daily(daily, "rain_sum", i),
            "wind_max_kmh": _daily(daily, "wind_speed_10m_max", i), "weather_code": _daily(daily, "weather_code", i),
        })
    for rec in ([current] if current else []) + days:
        _check_ranges(rec, problems)
    return current, days, problems


def parse_forecast(payload: dict, today: date | None = None) -> tuple[list[dict], list[str]]:
    """Provider forecasts for today (incomplete) and later days. These are model predictions."""
    today = today or today_ist()
    out, problems = [], []
    daily = payload.get("daily") or {}
    for i, t in enumerate(daily.get("time") or []):
        start = datetime.fromtimestamp(int(t), IST)
        if start.date() < today:
            continue
        rec = {
            "observed_at": start.astimezone(UTC), "obs_date": start.date(),
            "temp_max_c": _daily(daily, "temperature_2m_max", i), "temp_min_c": _daily(daily, "temperature_2m_min", i),
            "precipitation_mm": _daily(daily, "precipitation_sum", i), "rain_mm": _daily(daily, "rain_sum", i),
            "precipitation_probability": _daily(daily, "precipitation_probability_max", i),
            "wind_max_kmh": _daily(daily, "wind_speed_10m_max", i), "weather_code": _daily(daily, "weather_code", i),
        }
        _check_ranges(rec, problems)
        out.append(rec)
    return out, problems


def _upsert_weather(db, run, wh, kind, key, rec, fetched_at, endpoint, notes, counts: dict, count_as_observation: bool):
    obs = db.scalar(select(WeatherObservation).where(WeatherObservation.dedupe_key == key))
    status = ValidationStatus.ACCEPTED_WITH_WARNING if notes else ValidationStatus.ACCEPTED
    raw = {k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in rec.items()}
    prov = {"source_endpoint": endpoint, "raw_reference": raw, "validation_status": status,
            "validation_notes": notes or None}
    if obs is None:
        db.add(WeatherObservation(dedupe_key=key, organization_id=run.organization_id, warehouse_id=wh.id,
                                  source_id=run.source_id, run_id=run.id, kind=kind, latitude=wh.latitude,
                                  longitude=wh.longitude, fetched_at=fetched_at, **rec, **prov))
        counts["inserted" if count_as_observation else "forecasts"] += 1
        return
    changed = any(getattr(obs, k) != v for k, v in rec.items() if k != "observed_at")
    for k, v in {**rec, **prov}.items():
        setattr(obs, k, v)
    obs.fetched_at, obs.run_id = fetched_at, run.id
    if not count_as_observation:
        counts["forecasts"] += 1
    elif changed:
        counts["updated"] += 1
    else:
        counts["unchanged"] += 1


def fetch_open_meteo(db: Session, run: IngestionRun, client: httpx.Client) -> None:
    settings = get_settings()
    fetched_at = utcnow()
    run.endpoint = endpoint_for(OPEN_METEO)
    stmt = select(Warehouse).where(Warehouse.organization_id == run.organization_id,
                                   Warehouse.latitude.is_not(None), Warehouse.longitude.is_not(None))
    ids = run.params.get("warehouse_ids")
    if ids is not None:
        stmt = stmt.where(Warehouse.id.in_([uuid.UUID(i) for i in ids] or [uuid.UUID(int=0)]))
    warehouses = db.scalars(stmt).unique().all()
    if not warehouses:
        raise ConnectorError("No warehouses with coordinates. Add latitude/longitude to a warehouse first.", "NO_LOCATIONS")

    failures, kinds, first_error = 0, set(), None
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "forecasts": 0}
    today = today_ist()
    for idx, wh in enumerate(warehouses, start=1):
        params = {"latitude": wh.latitude, "longitude": wh.longitude, "current": OPEN_METEO_CURRENT,
                  "daily": OPEN_METEO_DAILY, "past_days": 7, "forecast_days": 3,
                  "timezone": "Asia/Kolkata", "timeformat": "unixtime"}
        endpoint = f"{settings.open_meteo_base}?latitude={wh.latitude}&longitude={wh.longitude}"
        try:
            payload = get_json(client, settings.open_meteo_base, params, "Open-Meteo")
            if "current" not in payload and "daily" not in payload:
                raise ConnectorError("Open-Meteo response has neither 'current' nor 'daily' data", "MALFORMED")
            current, days, problems = parse_open_meteo(payload, today)
            forecasts, fproblems = parse_forecast(payload, today)
        except ConnectorError as e:
            failures += 1
            kinds.add(e.kind)
            first_error = first_error or str(e)
            db.add(IngestionIssue(run_id=run.id, row_number=idx, field="location", severity=IssueSeverity.ERROR,
                                  code=f"FETCH_{e.kind}", message=f"{wh.name}: {e}", raw={"warehouse": wh.name}))
            continue
        except (ValueError, KeyError, TypeError) as e:
            failures += 1
            kinds.add("MALFORMED")
            first_error = first_error or f"unreadable response ({type(e).__name__})"
            db.add(IngestionIssue(run_id=run.id, row_number=idx, field="location", severity=IssueSeverity.ERROR,
                                  code="FETCH_MALFORMED", message=f"{wh.name}: unreadable response ({type(e).__name__})",
                                  raw={"warehouse": wh.name}))
            continue
        for p in problems + fproblems:
            run.warnings += 1
            db.add(IngestionIssue(run_id=run.id, row_number=idx, field="value", severity=IssueSeverity.WARNING,
                                  code="OUT_OF_RANGE", message=f"{wh.name}: {p} (value dropped)", raw={"warehouse": wh.name}))
        cur_notes: list[str] = []
        if current:
            if current["observed_at"] > fetched_at + timedelta(hours=1):
                run.rows_rejected += 1
                db.add(IngestionIssue(run_id=run.id, row_number=idx, field="current.time", severity=IssueSeverity.ERROR,
                                      code="FUTURE_TIMESTAMP",
                                      message=f"{wh.name}: reading time {current['observed_at'].isoformat()} is in the future",
                                      raw={"warehouse": wh.name}))
                current = None
            elif fetched_at - current["observed_at"] > timedelta(hours=3):
                msg = f"{wh.name}: provider returned a reading from {current['observed_at'].isoformat()} (over 3h old)"
                cur_notes.append(msg)
                run.warnings += 1
                db.add(IngestionIssue(run_id=run.id, row_number=idx, field="current.time", severity=IssueSeverity.WARNING,
                                      code="STALE_READING", message=msg, raw={"warehouse": wh.name}))
        run.rows_received += (1 if current else 0) + len(days)
        if current:
            _upsert_weather(db, run, wh, WeatherKind.CURRENT, _key(wh.id, "CURRENT", current["observed_at"].isoformat()),
                            current, fetched_at, endpoint, cur_notes, counts, True)
        for d in days:
            _upsert_weather(db, run, wh, WeatherKind.DAILY, _key(wh.id, "DAILY", d["obs_date"].isoformat()),
                            d, fetched_at, endpoint, [], counts, True)
        for f in forecasts:
            _upsert_weather(db, run, wh, WeatherKind.FORECAST, _key(wh.id, "FORECAST", f["obs_date"].isoformat()),
                            f, fetched_at, endpoint, [], counts, False)
    run.rows_inserted, run.rows_updated, run.rows_unchanged = counts["inserted"], counts["updated"], counts["unchanged"]
    run.rows_duplicate = counts["unchanged"]
    run.rows_rejected += failures
    run.params = {**run.params, "locations": len(warehouses), "failed_locations": failures,
                  "forecast_days_stored": counts["forecasts"]}
    if failures == len(warehouses):
        kind = kinds.pop() if len(kinds) == 1 else "NETWORK"
        raise ConnectorError(f"Could not fetch Open-Meteo for any of {len(warehouses)} warehouse locations"
                             + (f" — {first_error}" if first_error else ""), kind)


CONNECTORS: dict[str, Callable[[Session, IngestionRun, httpx.Client], None]] = {
    OGD_MANDI: fetch_ogd_mandi,
    OPEN_METEO: fetch_open_meteo,
}


def execute_run(session_factory, run_id: uuid.UUID) -> None:
    """Run a connector for an existing RUNNING run and record the outcome. Never raises."""
    with session_factory() as db:
        run = db.get(IngestionRun, run_id)
        if run is None:
            return
        connector = CONNECTORS[run.source.key]
        try:
            with make_client() as client:
                connector(db, run, client)
            run.status = RunStatus.PARTIAL if run.rows_rejected else RunStatus.SUCCESS
        except ConnectorError as e:
            db.rollback()
            run = db.get(IngestionRun, run_id)
            run.status, run.error_message, run.error_kind = RunStatus.FAILED, _redact(str(e))[:1000], e.kind
            run.endpoint = endpoint_for(run.source.key)
        except Exception as e:  # noqa: BLE001 - recorded, not swallowed silently
            log.exception("Ingestion run %s failed", run_id)
            db.rollback()
            run = db.get(IngestionRun, run_id)
            run.status, run.error_kind = RunStatus.FAILED, "UNEXPECTED"
            run.error_message = _redact(f"Unexpected error: {type(e).__name__}")
        run.finished_at = datetime.now(UTC)
        db.commit()


def ensure_active_commodity_names(db: Session, org_id) -> list[str]:
    rows = db.scalars(select(Commodity).where(Commodity.organization_id == org_id,
                                              Commodity.status == RecordStatus.ACTIVE))
    return [c.market_name or c.name for c in rows]
