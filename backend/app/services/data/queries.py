"""Read-side queries for external data, shared by the API routes and the dashboards.

Visibility rules (the same everywhere):
- market prices: official public rows (organization_id NULL) + the caller's own uploads
- weather: the caller's organization, limited to warehouses in their location scope
- ingestion runs: the caller's organization + shared public fetches (organization_id NULL);
  who triggered a public fetch is only shown to members of that person's organization
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.models import (
    Commodity,
    DataSource,
    IngestionRun,
    InventoryItem,
    MarketPrice,
    Warehouse,
    WeatherObservation,
)
from app.models.enums import (
    DataClass,
    DataKind,
    DataOrigin,
    RecordStatus,
    RunStatus,
    SourceOrigin,
    WeatherKind,
)
from app.schemas import Ref
from app.schemas.data import (
    Compare,
    CompareRow,
    DataEnvironment,
    EnvironmentItem,
    ForecastDay,
    IssueOut,
    LatestPrice,
    PriceDetail,
    PriceOut,
    RunDetail,
    RunOut,
    SourceRef,
    SourceStatus,
    Trend,
    TrendPoint,
    TrendSeries,
    WeatherDay,
    WeatherHistory,
    WeatherNow,
    WeatherReading,
)
from app.services.data import freshness as fr
from app.services.data import indicators
from app.services.data import scheduler as sched
from app.services.data.connectors import endpoint_for, is_configured
from app.services.data.sources import CSV_INVENTORY, CSV_MARKET, FETCHABLE, OGD_MANDI, OPEN_METEO
from app.services.rbac import P

WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers", 81: "Showers",
    82: "Violent showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}

EXPECTED_REFRESH = {
    OGD_MANDI: "Daily dataset — fetched 3× a day (10:30, 14:30, 19:30 IST)",
    OPEN_METEO: "Hourly (provider updates current conditions every 15 min)",
    CSV_MARKET: "On upload",
    CSV_INVENTORY: "On upload",
}


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def source_ref(src: DataSource | None) -> SourceRef | None:
    return SourceRef(key=src.key, name=src.name, origin=src.origin.value) if src else None


def class_for_source(src: DataSource | None) -> DataClass:
    if src is None:
        return DataClass.UNAVAILABLE
    return DataClass.REAL_ORGANIZATION if src.origin == SourceOrigin.USER_UPLOAD else DataClass.REAL_EXTERNAL


def market_freshness(src: DataSource, latest: date | None) -> fr.Freshness:
    """Uploaded files are historical snapshots, never a "daily" feed."""
    if latest is None:
        return fr.unavailable()
    if src.origin == SourceOrigin.USER_UPLOAD:
        return fr.Freshness(label="HISTORICAL", tone="neutral",
                            detail=f"Uploaded file · latest date {latest.strftime('%d %b %Y')}")
    return fr.for_daily(latest)


def visible_prices(ctx: AuthContext):
    return or_(MarketPrice.organization_id.is_(None), MarketPrice.organization_id == ctx.org_id)


def visible_runs(ctx: AuthContext):
    return or_(IngestionRun.organization_id == ctx.org_id, IngestionRun.organization_id.is_(None))


def run_out(run: IngestionRun, ctx: AuthContext | None = None) -> RunOut:
    dur = (_aware(run.finished_at) - _aware(run.started_at)).total_seconds() if run.finished_at else None
    who = None
    if run.triggered_by and (ctx is None or run.triggered_by.organization_id == ctx.org_id):
        who = run.triggered_by.full_name
    elif run.triggered_by:
        who = "Another workspace"
    return RunOut(
        id=run.id, source=source_ref(run.source), trigger=run.trigger.value, status=run.status.value,
        started_at=run.started_at, finished_at=run.finished_at, duration_seconds=dur,
        rows_received=run.rows_received, rows_inserted=run.rows_inserted, rows_updated=run.rows_updated,
        rows_unchanged=run.rows_unchanged, rows_rejected=run.rows_rejected, rows_duplicate=run.rows_duplicate or 0,
        warnings=run.warnings, error_message=run.error_message, error_kind=run.error_kind, endpoint=run.endpoint,
        scope="PUBLIC" if run.organization_id is None else "ORGANIZATION", file_name=run.file_name,
        triggered_by=who, params={k: v for k, v in (run.params or {}).items() if k != "warehouse_ids"},
    )


def run_detail(run: IngestionRun, issues, ctx: AuthContext | None = None) -> RunDetail:
    return RunDetail(**run_out(run, ctx).model_dump(), issues=[
        IssueOut(row_number=i.row_number, field=i.field, severity=i.severity.value, code=i.code,
                 message=i.message, raw=i.raw) for i in issues])


# --------------------------------------------------------------------------- source state & health


@dataclass
class SourceState:
    last_run: IngestionRun | None
    last_success: IngestionRun | None
    last_failure: IngestionRun | None

    @property
    def failing(self) -> bool:
        """The most recent finished fetch failed (after any success)."""
        if self.last_failure is None:
            return False
        if self.last_success is None:
            return True
        return _aware(self.last_failure.started_at) > _aware(self.last_success.started_at)


def _runs_query(src: DataSource, ctx: AuthContext):
    q = select(IngestionRun).where(IngestionRun.source_id == src.id)
    if src.key == OGD_MANDI:
        # Shared public fetches, plus any this organization triggered before V3.
        return q.where(visible_runs(ctx))
    return q.where(IngestionRun.organization_id == ctx.org_id)


def source_state(db: Session, src: DataSource, ctx: AuthContext) -> SourceState:
    q = _runs_query(src, ctx)
    last = db.scalars(q.order_by(IngestionRun.started_at.desc()).limit(1)).first()
    ok = db.scalars(q.where(IngestionRun.status.in_([RunStatus.SUCCESS, RunStatus.PARTIAL]))
                    .order_by(IngestionRun.started_at.desc()).limit(1)).first()
    bad = db.scalars(q.where(IngestionRun.status == RunStatus.FAILED)
                     .order_by(IngestionRun.started_at.desc()).limit(1)).first()
    return SourceState(last, ok, bad)


def _state_for_key(db, ctx, key) -> tuple[DataSource | None, SourceState | None]:
    src = db.scalar(select(DataSource).where(DataSource.key == key))
    return (src, source_state(db, src, ctx)) if src else (None, None)


def source_statuses(db: Session, ctx: AuthContext) -> list[SourceStatus]:
    running, beat = sched.scheduler_status(db)
    out = []
    for src in db.scalars(select(DataSource).order_by(DataSource.origin, DataSource.name)):
        configured, msg = is_configured(src.key)
        st = source_state(db, src, ctx)
        upload = src.origin == SourceOrigin.USER_UPLOAD

        count, latest, fresh, verified_at = 0, None, None, None
        if src.kind == DataKind.MARKET_PRICES:
            q = select(func.count(), func.max(MarketPrice.arrival_date)).where(
                MarketPrice.source_id == src.id, visible_prices(ctx))
            count, latest_date = db.execute(q).one()
            latest = latest_date.isoformat() if latest_date else None
            verified_at = latest_date
            fresh = market_freshness(src, latest_date) if latest_date else fr.unavailable(
                "Not configured" if not configured else "No verified mandi price available yet")
        elif src.kind == DataKind.WEATHER:
            scope = [WeatherObservation.source_id == src.id, WeatherObservation.organization_id == ctx.org_id,
                     ctx.warehouse_filter(WeatherObservation.warehouse_id)]
            count = db.scalar(select(func.count()).select_from(WeatherObservation).where(*scope))
            latest_at = db.scalar(select(func.max(WeatherObservation.observed_at)).where(
                *scope, WeatherObservation.kind == WeatherKind.CURRENT))
            latest = latest_at.isoformat() if latest_at else None
            verified_at = latest_at
            fresh = fr.for_reading(latest_at) if latest_at else fr.unavailable("Waiting for first successful fetch")
        else:
            count = db.scalar(select(func.count()).select_from(IngestionRun).where(
                IngestionRun.source_id == src.id, IngestionRun.organization_id == ctx.org_id)) or 0
        if not upload and st.failing:
            reason = st.last_failure.error_message if st.last_failure else None
            # ERROR = we have verified data but the latest update failed. No data at all stays UNAVAILABLE
            # (the source status says FAILING and carries the reason).
            fresh = fr.failed(verified_at, reason) if verified_at else fr.unavailable(
                f"Latest fetch failed: {reason}" if reason else "Latest fetch failed")

        if upload:
            status, detail = "UPLOAD_ONLY", "Filled by uploading a CSV file"
        elif not src.is_enabled:
            status, detail = "DISABLED", "Disabled by the administrator"
        elif not configured:
            status, detail = "NOT_CONFIGURED", msg or "Not configured"
        elif st.last_run is None:
            status, detail = "NOT_CONNECTED", "Waiting for first successful fetch"
        elif st.last_run.status == RunStatus.RUNNING:
            status, detail = ("FAILING" if st.failing else "CONNECTED"), "Fetch in progress"
        elif st.failing:
            status = "FAILING"
            detail = f"Latest fetch failed ({st.last_failure.error_kind or 'error'}): {st.last_failure.error_message}"
        elif st.last_success and st.last_success.status == RunStatus.PARTIAL:
            status, detail = "DEGRADED", "Last fetch succeeded with some rows or locations rejected"
        else:
            status, detail = "CONNECTED", "Last fetch succeeded"

        if src.key == OGD_MANDI:
            auth = "MISSING" if not configured else (
                "REJECTED" if st.failing and st.last_failure and st.last_failure.error_kind == "AUTH" else "CONFIGURED")
        else:
            auth = "NOT_REQUIRED"
        fetchable = src.key in FETCHABLE
        last_ok = st.last_success
        out.append(SourceStatus(
            key=src.key, name=src.name, publisher=src.publisher, kind=src.kind.value, origin=src.origin.value,
            homepage_url=src.homepage_url, license=src.license, update_frequency=src.update_frequency,
            description=src.description, configured=configured, config_message=msg,
            can_run=fetchable and configured and src.is_enabled and ctx.has(P.DATA_INGEST),
            can_upload=(src.key == CSV_MARKET and ctx.has(P.DATA_IMPORT))
            or (src.key == CSV_INVENTORY and ctx.has(P.INVENTORY_CREATE) and ctx.has(P.INVENTORY_UPDATE)),
            record_count=count or 0, latest_observation=latest, freshness=fresh,
            last_run=run_out(st.last_run, ctx) if st.last_run else None,
            last_success_at=_aware(last_ok.finished_at) if last_ok else None,
            data_class=class_for_source(src).value, status=status, status_detail=detail,
            endpoint=endpoint_for(src.key) if fetchable else None, auth_status=auth, enabled=src.is_enabled,
            auto_refresh=sched.auto_refresh_enabled(db, ctx.org_id, src.key) if fetchable else None,
            can_configure=fetchable and ctx.has(P.DATA_INGEST),
            expected_refresh=EXPECTED_REFRESH.get(src.key, ""),
            last_fetch_started_at=st.last_run.started_at if st.last_run else None,
            last_fetch_completed_at=st.last_run.finished_at if st.last_run else None,
            last_failure_at=(st.last_failure.finished_at or st.last_failure.started_at) if st.last_failure else None,
            last_failure_message=st.last_failure.error_message if st.last_failure else None,
            last_failure_kind=st.last_failure.error_kind if st.last_failure else None,
            last_rows_received=last_ok.rows_received if last_ok else None,
            last_rows_accepted=(last_ok.rows_inserted + last_ok.rows_updated + last_ok.rows_unchanged) if last_ok else None,
            last_rows_rejected=last_ok.rows_rejected if last_ok else None,
            last_rows_duplicate=(last_ok.rows_duplicate or 0) if last_ok else None,
            next_scheduled_at=sched.next_scheduled_at(db, src.key, ctx.org_id) if fetchable else None,
            scheduler_running=running, scheduler_heartbeat_at=beat,
        ))
    return out


# --------------------------------------------------------------------------- market prices


def catalog_names(db: Session, ctx: AuthContext) -> list[str]:
    rows = db.scalars(select(Commodity).where(Commodity.organization_id == ctx.org_id,
                                              Commodity.status == RecordStatus.ACTIVE).order_by(Commodity.name))
    return [c.market_name or c.name for c in rows]


def _stats_on(db, ctx, commodity: str, source_id, day: date):
    q = select(func.avg(MarketPrice.modal_price), func.min(MarketPrice.modal_price),
               func.max(MarketPrice.modal_price), func.count(func.distinct(MarketPrice.market)),
               func.max(MarketPrice.fetched_at)).where(
        visible_prices(ctx), func.lower(MarketPrice.commodity) == commodity.lower(),
        MarketPrice.source_id == source_id, MarketPrice.arrival_date == day)
    return db.execute(q).one()


def _market_fresh(db, ctx, src: DataSource, latest: date | None) -> fr.Freshness:
    f = market_freshness(src, latest)
    if src.origin != SourceOrigin.USER_UPLOAD:
        st = source_state(db, src, ctx)
        if st.failing and latest is not None:
            return fr.failed(latest, st.last_failure.error_message if st.last_failure else None)
    return f


def latest_prices(db: Session, ctx: AuthContext, commodities: list[str] | None = None) -> list[LatestPrice]:
    catalog = {n.lower() for n in catalog_names(db, ctx)}
    names = commodities if commodities is not None else catalog_names(db, ctx)
    out: list[LatestPrice] = []
    for name in names:
        per_source = db.execute(
            select(MarketPrice.source_id, func.max(MarketPrice.arrival_date))
            .where(visible_prices(ctx), func.lower(MarketPrice.commodity) == name.lower())
            .group_by(MarketPrice.source_id)
        ).all()
        if not per_source:
            out.append(LatestPrice(commodity=name, in_catalog=name.lower() in catalog, source=None,
                                   latest_date=None, markets_reporting=0, avg_modal=None, min_modal=None,
                                   max_modal=None, previous_date=None, previous_avg_modal=None, change_pct=None,
                                   fetched_at=None, data_class=DataClass.UNAVAILABLE.value,
                                   freshness=fr.unavailable("No verified mandi price available")))
            continue
        sources = {s.id: s for s in db.scalars(select(DataSource).where(
            DataSource.id.in_([sid for sid, _ in per_source])))}
        for source_id, latest in sorted(per_source, key=lambda r: sources[r[0]].origin != SourceOrigin.OFFICIAL_API):
            avg, lo, hi, markets, fetched = _stats_on(db, ctx, name, source_id, latest)
            prev_date = db.scalar(select(func.max(MarketPrice.arrival_date)).where(
                visible_prices(ctx), func.lower(MarketPrice.commodity) == name.lower(),
                MarketPrice.source_id == source_id, MarketPrice.arrival_date < latest))
            prev_avg = _stats_on(db, ctx, name, source_id, prev_date)[0] if prev_date else None
            change = round((float(avg) - float(prev_avg)) / float(prev_avg) * 100, 1) if prev_avg else None
            src = sources[source_id]
            out.append(LatestPrice(
                commodity=name, in_catalog=name.lower() in catalog, source=source_ref(src),
                latest_date=latest, markets_reporting=markets, avg_modal=round(float(avg), 2),
                min_modal=float(lo), max_modal=float(hi), previous_date=prev_date,
                previous_avg_modal=round(float(prev_avg), 2) if prev_avg else None, change_pct=change,
                change_abs=round(float(avg) - float(prev_avg), 2) if prev_avg else None,
                fetched_at=fetched, freshness=_market_fresh(db, ctx, src, latest),
                data_class=class_for_source(src).value))
    return out


def _pick_source(db, ctx, commodity: str, source_key: str | None) -> DataSource | None:
    q = select(DataSource).join(MarketPrice, MarketPrice.source_id == DataSource.id).where(
        visible_prices(ctx), func.lower(MarketPrice.commodity) == commodity.lower())
    if source_key:
        q = q.where(DataSource.key == source_key)
    candidates = db.scalars(q.distinct()).all()
    return sorted(candidates, key=lambda s: s.origin != SourceOrigin.OFFICIAL_API)[0] if candidates else None


def price_trend(db: Session, ctx: AuthContext, commodity: str, source_key: str | None,
                markets: list[str], days: int) -> Trend:
    src = _pick_source(db, ctx, commodity, source_key)
    if src is None:
        return Trend(commodity=commodity, source=None, series=[], freshness=fr.unavailable(
            "No verified mandi price available"))
    base = [visible_prices(ctx), func.lower(MarketPrice.commodity) == commodity.lower(),
            MarketPrice.source_id == src.id]
    latest = db.scalar(select(func.max(MarketPrice.arrival_date)).where(*base))
    since = latest - timedelta(days=days - 1)
    base.append(MarketPrice.arrival_date >= since)

    def points(extra) -> list[TrendPoint]:
        q = (select(MarketPrice.arrival_date, func.avg(MarketPrice.modal_price), func.min(MarketPrice.min_price),
                    func.max(MarketPrice.max_price), func.count(func.distinct(MarketPrice.market)))
             .where(*base, *extra).group_by(MarketPrice.arrival_date).order_by(MarketPrice.arrival_date))
        return [TrendPoint(date=d, modal=round(float(m), 2), low=float(lo) if lo is not None else None,
                           high=float(hi) if hi is not None else None, markets=n) for d, m, lo, hi, n in db.execute(q)]

    if markets:
        series = [TrendSeries(label=m, points=points([MarketPrice.market == m])) for m in markets[:3]]
    else:
        n = db.scalar(select(func.count(func.distinct(MarketPrice.market))).where(*base)) or 0
        series = [TrendSeries(label=f"Average across {n} market{'s' if n != 1 else ''}", points=points([]))]
    return Trend(commodity=commodity, source=source_ref(src), series=series, freshness=_market_fresh(db, ctx, src, latest))


GROUP_COLUMNS = {"market": MarketPrice.market, "district": MarketPrice.district, "state": MarketPrice.state}


def compare(db: Session, ctx: AuthContext, commodity: str, by: str, days: int, source_key: str | None) -> Compare:
    """Latest verified report per market/district/state within the window — no interpolation."""
    col = GROUP_COLUMNS[by]
    src = _pick_source(db, ctx, commodity, source_key)
    if src is None:
        return Compare(commodity=commodity, by=by, source=None, window_days=days, rows=[],
                       freshness=fr.unavailable("No verified mandi price available"))
    base = [visible_prices(ctx), func.lower(MarketPrice.commodity) == commodity.lower(), MarketPrice.source_id == src.id,
            col != ""]
    latest = db.scalar(select(func.max(MarketPrice.arrival_date)).where(*base))
    base.append(MarketPrice.arrival_date >= latest - timedelta(days=days - 1))
    last_per_group = (select(col.label("g"), func.max(MarketPrice.arrival_date).label("d"))
                      .where(*base).group_by(col).subquery())
    q = (select(col, MarketPrice.arrival_date, func.avg(MarketPrice.modal_price), func.min(MarketPrice.min_price),
                func.max(MarketPrice.max_price), func.count())
         .join(last_per_group, (col == last_per_group.c.g) & (MarketPrice.arrival_date == last_per_group.c.d))
         .where(*base).group_by(col, MarketPrice.arrival_date))
    rows = [CompareRow(name=g, latest_date=d, modal=round(float(m), 2), low=float(lo) if lo is not None else None,
                       high=float(hi) if hi is not None else None, reports=n) for g, d, m, lo, hi, n in db.execute(q)]
    rows.sort(key=lambda r: -r.modal)
    return Compare(commodity=commodity, by=by, source=source_ref(src), window_days=days, rows=rows,
                   freshness=_market_fresh(db, ctx, src, latest))


def price_out(r: MarketPrice) -> PriceOut:
    return PriceOut(
        id=r.id, state=r.state, district=r.district, market=r.market, commodity=r.commodity, variety=r.variety,
        grade=r.grade, arrival_date=r.arrival_date, min_price=float(r.min_price) if r.min_price is not None else None,
        max_price=float(r.max_price) if r.max_price is not None else None, modal_price=float(r.modal_price),
        unit=r.unit or "INR/quintal", source=source_ref(r.source), fetched_at=r.fetched_at,
        data_class=class_for_source(r.source).value, validation_status=r.validation_status.value,
        validation_notes=r.validation_notes, run_id=r.run_id)


def price_detail(db: Session, ctx: AuthContext, r: MarketPrice) -> PriceDetail:
    run = db.get(IngestionRun, r.run_id) if r.run_id else None
    visible = run is not None and (run.organization_id is None or run.organization_id == ctx.org_id)
    return PriceDetail(**price_out(r).model_dump(), source_record_id=r.source_record_id,
                       source_dataset=r.source_dataset, source_endpoint=r.source_endpoint,
                       raw_reference=r.raw_reference, publisher=r.source.publisher,
                       run=run_out(run, ctx) if visible else None)


# --------------------------------------------------------------------------- weather


def _weather_source(db) -> DataSource | None:
    return db.scalar(select(DataSource).where(DataSource.key == OPEN_METEO))


def _forecast(db, warehouse_id) -> list[ForecastDay]:
    rows = db.scalars(select(WeatherObservation).where(
        WeatherObservation.warehouse_id == warehouse_id, WeatherObservation.kind == WeatherKind.FORECAST,
        WeatherObservation.obs_date >= fr.today_ist()).order_by(WeatherObservation.obs_date).limit(3)).unique().all()
    return [ForecastDay(date=r.obs_date, temp_max_c=r.temp_max_c, temp_min_c=r.temp_min_c,
                        precipitation_mm=r.precipitation_mm, precipitation_probability=r.precipitation_probability,
                        wind_max_kmh=r.wind_max_kmh, weather_code=r.weather_code,
                        condition=WMO.get(r.weather_code) if r.weather_code is not None else None,
                        issued_at=r.fetched_at) for r in rows]


def weather_now(db: Session, ctx: AuthContext, region_id=None, warehouse_id=None) -> list[WeatherNow]:
    src = _weather_source(db)
    st = source_state(db, src, ctx) if src else None
    stmt = select(Warehouse).where(Warehouse.organization_id == ctx.org_id, ctx.warehouse_filter(Warehouse.id))
    if region_id:
        stmt = stmt.where(Warehouse.region_id == region_id)
    if warehouse_id:
        stmt = stmt.where(Warehouse.id == warehouse_id)
    warehouses = db.scalars(stmt.order_by(Warehouse.name)).unique().all()
    out = []
    for w in warehouses:
        obs = db.scalars(select(WeatherObservation).where(
            WeatherObservation.warehouse_id == w.id, WeatherObservation.kind == WeatherKind.CURRENT)
            .order_by(WeatherObservation.observed_at.desc()).limit(1)).first()
        reading = None
        if obs:
            reading = WeatherReading(observed_at=obs.observed_at, temperature_c=obs.temperature_c,
                                     humidity_pct=obs.humidity_pct, precipitation_mm=obs.precipitation_mm,
                                     rain_mm=obs.rain_mm, wind_kmh=obs.wind_kmh, wind_gust_kmh=obs.wind_gust_kmh,
                                     weather_code=obs.weather_code,
                                     condition=WMO.get(obs.weather_code) if obs.weather_code is not None else None,
                                     fetched_at=obs.fetched_at, run_id=obs.run_id,
                                     validation_status=obs.validation_status.value)
        stale = False
        if w.latitude is None or w.longitude is None:
            fresh = fr.unavailable("Add coordinates to this warehouse to fetch weather")
        elif st and st.failing:
            reason = st.last_failure.error_message if st.last_failure else None
            if obs:
                fresh = fr.failed(obs.observed_at, reason)
                stale = fr.for_reading(obs.observed_at).label == "HISTORICAL"
            else:
                fresh = fr.unavailable(f"Latest fetch failed: {reason}" if reason else "Latest fetch failed")
        else:
            fresh = fr.for_reading(obs.observed_at) if obs else fr.unavailable("Waiting for first successful fetch")
            stale = fresh.label == "HISTORICAL"
        days = db.scalars(select(WeatherObservation).where(
            WeatherObservation.warehouse_id == w.id, WeatherObservation.kind == WeatherKind.DAILY)
            .order_by(WeatherObservation.obs_date.desc()).limit(3)).unique().all()
        forecast = _forecast(db, w.id)
        inds, note = indicators.evaluate(
            reading if not stale else None,
            [{"obs_date": d.obs_date, "precipitation_mm": d.precipitation_mm} for d in reversed(days)],
            forecast)
        if stale and reading is not None:
            note = "Latest reading is stale; current-condition indicators were not evaluated" + (f"; {note}" if note else "")
        out.append(WeatherNow(
            warehouse=Ref(id=w.id, name=w.name), region=Ref(id=w.region.id, name=w.region.name),
            latitude=w.latitude, longitude=w.longitude, reading=reading, freshness=fresh, source=source_ref(src),
            data_class=(DataClass.REAL_EXTERNAL if obs else DataClass.UNAVAILABLE).value, stale=stale,
            forecast=forecast, indicators=inds, indicators_note=note))
    return out


def weather_history(db: Session, ctx: AuthContext, warehouse: Warehouse, days: int) -> WeatherHistory:
    src = _weather_source(db)
    since = fr.today_ist() - timedelta(days=days)
    rows = db.scalars(select(WeatherObservation).where(
        WeatherObservation.warehouse_id == warehouse.id, WeatherObservation.kind == WeatherKind.DAILY,
        WeatherObservation.obs_date >= since).order_by(WeatherObservation.obs_date)).unique().all()
    return WeatherHistory(
        warehouse=Ref(id=warehouse.id, name=warehouse.name),
        days=[WeatherDay(date=r.obs_date, temp_max_c=r.temp_max_c, temp_min_c=r.temp_min_c,
                         precipitation_mm=r.precipitation_mm) for r in rows],
        source=source_ref(src),
        freshness=fr.for_daily(rows[-1].obs_date) if rows else fr.unavailable(),
    )


# --------------------------------------------------------------------------- data environment


def origin_counts(db: Session, ctx: AuthContext, model, id_col) -> dict[str, int]:
    rows = db.execute(select(model.data_origin, func.count()).where(
        model.organization_id == ctx.org_id, ctx.warehouse_filter(id_col)).group_by(model.data_origin)).all()
    return {str(o.value if hasattr(o, "value") else o): n for o, n in rows}


def class_for_counts(counts: dict[str, int]) -> DataClass:
    synthetic = counts.get(DataOrigin.SYNTHETIC_DEMO.value, 0)
    real = sum(n for k, n in counts.items() if k != DataOrigin.SYNTHETIC_DEMO.value)
    if not synthetic and not real:
        return DataClass.UNAVAILABLE
    if synthetic and real:
        return DataClass.MIXED
    return DataClass.SYNTHETIC_DEMO if synthetic else DataClass.REAL_ORGANIZATION


def _org_item(key, label, counts, noun) -> EnvironmentItem:
    cls = class_for_counts(counts)
    synthetic = counts.get(DataOrigin.SYNTHETIC_DEMO.value, 0)
    real = sum(n for k, n in counts.items() if k != DataOrigin.SYNTHETIC_DEMO.value)
    text = {
        DataClass.UNAVAILABLE: ("none", f"No {noun} yet", f"Add {noun} manually or import a CSV."),
        DataClass.SYNTHETIC_DEMO: ("warn", "Synthetic demo data", f"All {synthetic} {noun} were created by the demo seed."),
        DataClass.MIXED: ("warn", "Mixed: synthetic + organization data",
                          f"{real} {noun} from your organization, {synthetic} synthetic demo {noun}."),
        DataClass.REAL_ORGANIZATION: ("ok", "Organization data", f"{real} {noun} entered or imported by your team."),
    }[cls]
    return EnvironmentItem(key=key, label=label, data_class=cls.value, status=text[0], summary=text[1],
                           detail=text[2], counts=counts)


def environment(db: Session, ctx: AuthContext) -> DataEnvironment:
    items: list[EnvironmentItem] = []
    syncs: list[datetime] = []

    # Market prices
    mandi, mst = _state_for_key(db, ctx, OGD_MANDI)
    official = db.execute(select(func.count(), func.max(MarketPrice.arrival_date)).where(
        MarketPrice.source_id == mandi.id)).one() if mandi else (0, None)
    upload_src = db.scalar(select(DataSource).where(DataSource.key == CSV_MARKET))
    uploaded = db.scalar(select(func.count()).select_from(MarketPrice).where(
        MarketPrice.source_id == upload_src.id, MarketPrice.organization_id == ctx.org_id)) if upload_src else 0
    if mst and mst.last_success:
        syncs.append(_aware(mst.last_success.finished_at))
    if official[0]:
        failing = mst.failing
        items.append(EnvironmentItem(
            key="market_prices", label="Market prices", data_class=DataClass.REAL_EXTERNAL.value,
            status="bad" if failing else "ok",
            summary="Real external data" + (" · latest fetch failed" if failing else ""),
            detail=f"AGMARKNET via data.gov.in · latest report {official[1]:%d %b %Y} · {official[0]:,} reports"
            + (f" · plus {uploaded:,} uploaded rows" if uploaded else ""),
            source="AGMARKNET (data.gov.in)", as_of=_aware(mst.last_success.finished_at) if mst.last_success else None))
    elif uploaded:
        items.append(EnvironmentItem(
            key="market_prices", label="Market prices", data_class=DataClass.REAL_ORGANIZATION.value, status="warn",
            summary="Uploaded files only", detail=f"{uploaded:,} rows from your uploads; no official data fetched yet.",
            source="Uploaded files"))
    else:
        configured = is_configured(OGD_MANDI)[0]
        items.append(EnvironmentItem(
            key="market_prices", label="Market prices", data_class=DataClass.UNAVAILABLE.value,
            status="bad" if (mst and mst.failing) else "none", summary="No verified mandi price available",
            detail=("Latest fetch failed: " + (mst.last_failure.error_message or "")) if (mst and mst.failing)
            else ("Waiting for first successful fetch" if configured else "Source not configured (DATA_GOV_IN_API_KEY)"),
            source="AGMARKNET (data.gov.in)"))

    # Weather
    wsrc, wst = _state_for_key(db, ctx, OPEN_METEO)
    wq = [WeatherObservation.organization_id == ctx.org_id, ctx.warehouse_filter(WeatherObservation.warehouse_id),
          WeatherObservation.kind == WeatherKind.CURRENT]
    latest_reading = db.scalar(select(func.max(WeatherObservation.observed_at)).where(*wq))
    if wst and wst.last_success:
        syncs.append(_aware(wst.last_success.finished_at))
    if latest_reading:
        f = fr.failed(latest_reading) if wst.failing else fr.for_reading(latest_reading)
        items.append(EnvironmentItem(
            key="weather", label="Weather", data_class=DataClass.REAL_EXTERNAL.value,
            status="bad" if wst.failing else ("ok" if f.label in ("CURRENT", "RECENT") else "warn"),
            summary="Real external data" + (" · latest fetch failed" if wst.failing else ""),
            detail=f"Open-Meteo · {f.detail}", source="Open-Meteo", as_of=_aware(latest_reading)))
    else:
        items.append(EnvironmentItem(
            key="weather", label="Weather", data_class=DataClass.UNAVAILABLE.value,
            status="bad" if (wst and wst.failing) else "none", summary="No verified weather data",
            detail=("Latest fetch failed: " + (wst.last_failure.error_message or "")) if (wst and wst.failing)
            else "Waiting for first successful fetch (warehouses need coordinates)", source="Open-Meteo"))

    # Organization data
    items.append(_org_item("inventory", "Inventory", origin_counts(db, ctx, InventoryItem, InventoryItem.warehouse_id),
                           "inventory records"))
    items.append(_org_item("warehouses", "Warehouse capacity", origin_counts(db, ctx, Warehouse, Warehouse.id),
                           "warehouses"))

    # Not collected yet
    items.append(EnvironmentItem(key="demand_history", label="Demand history", data_class=DataClass.UNAVAILABLE.value,
                                 status="none", summary="No verified historical data",
                                 detail="Demand data is not collected yet (planned for V4)."))
    items.append(EnvironmentItem(key="predictions", label="Model predictions", data_class=DataClass.UNAVAILABLE.value,
                                 status="none", summary="None",
                                 detail="No AgriFlow models are trained yet. Only the weather provider's own forecast is shown, "
                                        "labelled as a forecast."))
    return DataEnvironment(items=items, last_successful_sync=max(syncs) if syncs else None,
                           generated_at=datetime.now(UTC))


def stale_running(db: Session, source_id, org_id) -> IngestionRun | None:
    """A run for this source/org that is still RUNNING and started in the last 10 minutes."""
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    q = select(IngestionRun).where(IngestionRun.source_id == source_id, IngestionRun.status == RunStatus.RUNNING,
                                   IngestionRun.started_at >= cutoff)
    q = q.where(IngestionRun.organization_id.is_(None) if org_id is None else IngestionRun.organization_id == org_id)
    return db.scalars(q).first()


