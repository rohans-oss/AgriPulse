"""Connectors that fetch real public data, and the executor that records each run.

HTTP goes through ``make_client`` so tests can swap in recorded responses.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Commodity, IngestionIssue, IngestionRun, Warehouse, WeatherObservation
from app.models.enums import IssueSeverity, RecordStatus, RunStatus, WeatherKind
from app.services.data import market
from app.services.data.freshness import IST, today_ist
from app.services.data.sources import OGD_MANDI, OPEN_METEO

log = logging.getLogger(__name__)

MAX_OGD_PAGES = 20
OGD_PAGE_SIZE = 1000


class ConnectorError(Exception):
    """A failure whose message is safe to show to users."""


def make_client() -> httpx.Client:
    return httpx.Client(timeout=get_settings().http_timeout_seconds, headers={"User-Agent": "AgriFlowAI/2.0"})


def _redact(text: str) -> str:
    key = get_settings().data_gov_in_api_key
    return text.replace(key, "***") if key else text


def is_configured(source_key: str) -> tuple[bool, str | None]:
    if source_key == OGD_MANDI and not get_settings().data_gov_in_api_key:
        return False, "Set DATA_GOV_IN_API_KEY (free from data.gov.in) to enable this source"
    return True, None


# --------------------------------------------------------------------------- data.gov.in mandi prices


def fetch_ogd_mandi(db: Session, run: IngestionRun, client: httpx.Client) -> None:
    settings = get_settings()
    if not settings.data_gov_in_api_key:
        raise ConnectorError("DATA_GOV_IN_API_KEY is not configured")
    url = f"{settings.ogd_api_base}/{settings.ogd_mandi_resource_id}"
    fetched_at = datetime.now(UTC)
    states = run.params.get("states") or settings.mandi_states
    wanted = {s.strip().lower() for s in states}
    accepted: list[tuple[int, dict]] = []
    issues: list[dict] = []
    row_no = 0

    for state in states:
        offset = 0
        for _ in range(MAX_OGD_PAGES):
            params = {"api-key": settings.data_gov_in_api_key, "format": "json", "limit": OGD_PAGE_SIZE,
                      "offset": offset, "filters[state.keyword]": state}
            try:
                resp = client.get(url, params=params)
            except httpx.HTTPError as e:
                raise ConnectorError(f"Could not reach data.gov.in: {type(e).__name__}") from None
            if resp.status_code in (401, 403):
                raise ConnectorError("data.gov.in rejected the API key")
            if resp.status_code >= 400:
                raise ConnectorError(f"data.gov.in returned HTTP {resp.status_code}")
            try:
                payload = resp.json()
            except ValueError:
                raise ConnectorError("data.gov.in returned a response that is not JSON") from None
            if isinstance(payload, dict) and payload.get("error"):
                raise ConnectorError(f"data.gov.in error: {_redact(str(payload['error']))[:200]}")
            records = payload.get("records") or []
            for rec in records:
                row_no += 1
                # Guard in case the server ignored the state filter.
                rstate = str(rec.get("state") or rec.get("State") or "").strip().lower()
                if rstate and rstate not in wanted:
                    continue
                run.rows_received += 1
                res = market.validate_row(rec, row_no)
                issues += res.issues
                if res.clean:
                    accepted.append((row_no, res.clean))
            total = int(payload.get("total") or 0)
            offset += len(records)
            if not records or offset >= total:
                break

    run.params = {**run.params, "states": list(states), "resource_id": settings.ogd_mandi_resource_id}
    _finish_market(db, run, accepted, issues, None, fetched_at)


def _finish_market(db, run, accepted, issues, org_id, fetched_at):
    market.record_issues(db, run, issues)
    run.rows_rejected = sum(1 for i in issues if i["severity"] == IssueSeverity.ERROR)
    stats = market.upsert_prices(db, run, accepted, org_id, fetched_at)
    run.rows_inserted, run.rows_updated, run.rows_unchanged = stats.inserted, stats.updated, stats.unchanged
    run.warnings = stats.warnings + sum(1 for i in issues if i["severity"] == IssueSeverity.WARNING)


# --------------------------------------------------------------------------- Open-Meteo weather


def _key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _in_range(v, lo, hi) -> bool:
    return v is None or lo <= v <= hi


RANGES = {"temperature_c": (-40, 60), "humidity_pct": (0, 100), "precipitation_mm": (0, 1000),
          "wind_kmh": (0, 400), "temp_max_c": (-40, 60), "temp_min_c": (-40, 60)}


def parse_open_meteo(payload: dict, today: date | None = None) -> tuple[dict | None, list[dict], list[str]]:
    """Return (current, completed_days, problems) from an Open-Meteo forecast response."""
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
            "wind_kmh": cur.get("wind_speed_10m"),
            "weather_code": cur.get("weather_code"),
        }
    days = []
    daily = payload.get("daily") or {}
    for i, t in enumerate(daily.get("time") or []):
        start = datetime.fromtimestamp(int(t), IST)
        if start.date() >= today:  # today is incomplete, later days are forecasts: never stored
            continue
        days.append({
            "observed_at": start.astimezone(UTC),
            "obs_date": start.date(),
            "temp_max_c": (daily.get("temperature_2m_max") or [None] * (i + 1))[i],
            "temp_min_c": (daily.get("temperature_2m_min") or [None] * (i + 1))[i],
            "precipitation_mm": (daily.get("precipitation_sum") or [None] * (i + 1))[i],
        })
    for rec in ([current] if current else []) + days:
        for f, (lo, hi) in RANGES.items():
            if f in rec and not _in_range(rec[f], lo, hi):
                problems.append(f"{f}={rec[f]} outside plausible range {lo}..{hi}")
                rec[f] = None
    return current, days, problems


def fetch_open_meteo(db: Session, run: IngestionRun, client: httpx.Client) -> None:
    settings = get_settings()
    fetched_at = datetime.now(UTC)
    stmt = select(Warehouse).where(Warehouse.organization_id == run.organization_id,
                                   Warehouse.latitude.is_not(None), Warehouse.longitude.is_not(None))
    ids = run.params.get("warehouse_ids")
    if ids is not None:
        stmt = stmt.where(Warehouse.id.in_([uuid.UUID(i) for i in ids] or [uuid.UUID(int=0)]))
    warehouses = db.scalars(stmt).unique().all()
    if not warehouses:
        raise ConnectorError("No warehouses with coordinates. Add latitude/longitude to a warehouse first.")

    failures = 0
    for idx, wh in enumerate(warehouses, start=1):
        params = {
            "latitude": wh.latitude, "longitude": wh.longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "past_days": 7, "forecast_days": 1, "timezone": "Asia/Kolkata", "timeformat": "unixtime",
        }
        try:
            resp = client.get(settings.open_meteo_base, params=params)
            resp.raise_for_status()
            current, days, problems = parse_open_meteo(resp.json())
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            failures += 1
            db.add(IngestionIssue(run_id=run.id, row_number=idx, field="location", severity=IssueSeverity.ERROR,
                                  code="FETCH_FAILED", message=f"{wh.name}: {type(e).__name__}",
                                  raw={"warehouse": wh.name}))
            continue
        for p in problems:
            run.warnings += 1
            db.add(IngestionIssue(run_id=run.id, row_number=idx, field="value", severity=IssueSeverity.WARNING,
                                  code="OUT_OF_RANGE", message=f"{wh.name}: {p} (value dropped)",
                                  raw={"warehouse": wh.name}))
        records = []
        if current:
            records.append((WeatherKind.CURRENT, _key(wh.id, "CURRENT", current["observed_at"].isoformat()), current))
        for d in days:
            records.append((WeatherKind.DAILY, _key(wh.id, "DAILY", d["obs_date"].isoformat()), d))
        run.rows_received += len(records)
        for kind, key, rec in records:
            obs = db.scalar(select(WeatherObservation).where(WeatherObservation.dedupe_key == key))
            if obs is None:
                db.add(WeatherObservation(dedupe_key=key, organization_id=run.organization_id, warehouse_id=wh.id,
                                          source_id=run.source_id, run_id=run.id, kind=kind,
                                          latitude=wh.latitude, longitude=wh.longitude, fetched_at=fetched_at, **rec))
                run.rows_inserted += 1
            else:
                changed = any(getattr(obs, k) != v for k, v in rec.items() if k != "observed_at")
                for k, v in rec.items():
                    setattr(obs, k, v)
                obs.fetched_at, obs.run_id = fetched_at, run.id
                if changed:
                    run.rows_updated += 1
                else:
                    run.rows_unchanged += 1
    run.rows_rejected = failures
    run.params = {**run.params, "locations": len(warehouses)}
    if failures == len(warehouses):
        raise ConnectorError(f"Could not reach Open-Meteo for any of {len(warehouses)} warehouse locations")


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
            run.status, run.error_message = RunStatus.FAILED, _redact(str(e))[:1000]
        except Exception as e:  # noqa: BLE001 - recorded, not swallowed silently
            log.exception("Ingestion run %s failed", run_id)
            db.rollback()
            run = db.get(IngestionRun, run_id)
            run.status, run.error_message = RunStatus.FAILED, _redact(f"Unexpected error: {type(e).__name__}")
        run.finished_at = datetime.now(UTC)
        db.commit()


def ensure_active_commodity_names(db: Session, org_id) -> list[str]:
    rows = db.scalars(select(Commodity).where(Commodity.organization_id == org_id,
                                              Commodity.status == RecordStatus.ACTIVE))
    return [c.market_name or c.name for c in rows]
