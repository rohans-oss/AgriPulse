"""Automatic ingestion scheduling.

Stateless and restart-safe: what is "due" is computed from the ingestion-run history in the
database, so the worker can be stopped, restarted or run from cron without double-fetching.

- Weather (per organization with located warehouses): every WEATHER_REFRESH_MINUTES (default 60;
  Open-Meteo refreshes current conditions every 15 minutes, so hourly polling is plenty).
- Mandi prices (one shared public fetch): at MARKET_FETCH_TIMES_IST (default 10:30, 14:30, 19:30),
  because data.gov.in is updated through the day as mandis report — not more often.
- After a failure: retry after RETRY_AFTER_FAILURE_MINUTES (default 20), never in a tight loop.
- Organizations can switch automatic refresh off per source.
"""

import os
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    DataSource,
    IngestionRun,
    Organization,
    OrganizationSourceSetting,
    SchedulerState,
    Warehouse,
)
from app.models.enums import RunStatus, RunTrigger
from app.services.data.connectors import execute_run, is_configured
from app.services.data.freshness import IST
from app.services.data.sources import OGD_MANDI, OPEN_METEO, get_source

HEARTBEAT_KEY = "scheduler"
HEARTBEAT_FRESH = timedelta(minutes=3)
RUNNING_TIMEOUT = timedelta(minutes=10)


@dataclass(frozen=True)
class Job:
    source_key: str
    organization_id: uuid.UUID | None  # None = shared public fetch


def auto_refresh_enabled(db: Session, org_id, source_key: str) -> bool:
    row = db.scalar(select(OrganizationSourceSetting).where(
        OrganizationSourceSetting.organization_id == org_id, OrganizationSourceSetting.source_key == source_key))
    return True if row is None else row.auto_refresh


def _last_run(db: Session, source_id, org_id) -> IngestionRun | None:
    q = select(IngestionRun).where(IngestionRun.source_id == source_id,
                                   IngestionRun.trigger != RunTrigger.UPLOAD)
    q = q.where(IngestionRun.organization_id.is_(None) if org_id is None else IngestionRun.organization_id == org_id)
    return db.scalars(q.order_by(IngestionRun.started_at.desc()).limit(1)).first()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _market_slots(now: datetime) -> list[datetime]:
    """Today's and yesterday's scheduled market fetch times, in UTC, ascending."""
    local = now.astimezone(IST)
    slots = []
    for day in (local.date() - timedelta(days=1), local.date()):
        for t in get_settings().market_fetch_times_ist:
            hh, mm = (int(x) for x in t.split(":"))
            slots.append(datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST).astimezone(UTC))
    return sorted(slots)


def next_weather_at(last: IngestionRun | None, now: datetime) -> datetime:
    s = get_settings()
    if last is None:
        return now
    started = _aware(last.started_at)
    if last.status == RunStatus.FAILED:
        return started + timedelta(minutes=s.retry_after_failure_minutes)
    return started + timedelta(minutes=s.weather_refresh_minutes)


def next_market_at(last: IngestionRun | None, now: datetime) -> datetime:
    s = get_settings()
    if last is not None and last.status == RunStatus.FAILED:
        retry = _aware(last.started_at) + timedelta(minutes=s.retry_after_failure_minutes)
        # Retry a failed slot, but not past the next regular slot.
        upcoming = [t for t in _market_slots(now) + [t + timedelta(days=1) for t in _market_slots(now)] if t > _aware(last.started_at)]
        return min([retry] + upcoming[:1])
    last_start = _aware(last.started_at) if last else None
    past = [t for t in _market_slots(now) if t <= now]
    if past and (last_start is None or last_start < past[-1]):
        return past[-1]  # a slot has passed since the last fetch → due now
    future = [t for t in _market_slots(now) + [t + timedelta(days=1) for t in _market_slots(now)] if t > now]
    return future[0]


def _is_running(last: IngestionRun | None, now: datetime) -> bool:
    return bool(last and last.status == RunStatus.RUNNING and now - _aware(last.started_at) < RUNNING_TIMEOUT)


def plan(db: Session, now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(UTC)
    jobs: list[Job] = []

    weather = get_source(db, OPEN_METEO)
    if weather.is_enabled:
        org_ids = db.scalars(select(Warehouse.organization_id).where(
            Warehouse.latitude.is_not(None), Warehouse.longitude.is_not(None)).distinct()).all()
        for org_id in org_ids:
            if not auto_refresh_enabled(db, org_id, OPEN_METEO):
                continue
            last = _last_run(db, weather.id, org_id)
            if not _is_running(last, now) and next_weather_at(last, now) <= now:
                jobs.append(Job(OPEN_METEO, org_id))

    mandi = get_source(db, OGD_MANDI)
    configured, _ = is_configured(OGD_MANDI)
    if mandi.is_enabled and configured:
        org_ids = db.scalars(select(Organization.id)).all()
        wanted = any(auto_refresh_enabled(db, o, OGD_MANDI) for o in org_ids)
        last = _last_run(db, mandi.id, None)
        if wanted and not _is_running(last, now) and next_market_at(last, now) <= now:
            jobs.append(Job(OGD_MANDI, None))
    return jobs


def next_scheduled_at(db: Session, source_key: str, org_id, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(UTC)
    src = db.scalar(select(DataSource).where(DataSource.key == source_key))
    if src is None or not src.is_enabled:
        return None
    if source_key == OPEN_METEO:
        if not auto_refresh_enabled(db, org_id, OPEN_METEO):
            return None
        has_coords = db.scalar(select(func.count()).select_from(Warehouse).where(
            Warehouse.organization_id == org_id, Warehouse.latitude.is_not(None)))
        if not has_coords:
            return None
        return max(next_weather_at(_last_run(db, src.id, org_id), now), now)
    if source_key == OGD_MANDI:
        if not is_configured(OGD_MANDI)[0] or not auto_refresh_enabled(db, org_id, OGD_MANDI):
            return None
        return max(next_market_at(_last_run(db, src.id, None), now), now)
    return None


def start_job(db: Session, job: Job, trigger: RunTrigger = RunTrigger.SCHEDULED, params: dict | None = None) -> IngestionRun:
    run = IngestionRun(source_id=get_source(db, job.source_key).id, organization_id=job.organization_id,
                       trigger=trigger, params=params or {})
    db.add(run)
    db.commit()
    return run


def heartbeat(db: Session, **extra) -> None:
    state = db.get(SchedulerState, HEARTBEAT_KEY) or SchedulerState(key=HEARTBEAT_KEY, value={})
    state.value = {"host": socket.gethostname(), "pid": os.getpid(), "last_tick": datetime.now(UTC).isoformat(), **extra}
    state.updated_at = datetime.now(UTC)
    db.add(state)
    db.commit()


def scheduler_status(db: Session, now: datetime | None = None) -> tuple[bool, datetime | None]:
    now = now or datetime.now(UTC)
    state = db.get(SchedulerState, HEARTBEAT_KEY)
    if state is None:
        return False, None
    beat = _aware(state.updated_at)
    return now - beat <= HEARTBEAT_FRESH, beat


def run_due(session_factory, now: datetime | None = None) -> list[uuid.UUID]:
    """One scheduler tick: start every due job and run it to completion. Returns run ids."""
    with session_factory() as db:
        jobs = plan(db, now)
        run_ids = [start_job(db, j).id for j in jobs]
        heartbeat(db, jobs_started=len(run_ids))
    for rid in run_ids:
        execute_run(session_factory, rid)
    return run_ids
