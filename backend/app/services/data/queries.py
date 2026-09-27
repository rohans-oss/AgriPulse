"""Read-side queries for external data, shared by the API routes and the dashboards.

All queries apply the same visibility rules:
- market prices: official public rows (organization_id NULL) + the caller's own uploads
- weather: the caller's organization, limited to warehouses in their location scope
- ingestion runs: the caller's organization only
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.models import (
    Commodity,
    DataSource,
    IngestionRun,
    MarketPrice,
    Warehouse,
    WeatherObservation,
)
from app.models.enums import DataKind, RecordStatus, RunStatus, SourceOrigin, WeatherKind
from app.schemas import Ref
from app.schemas.data import (
    IssueOut,
    LatestPrice,
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
from app.services.data.connectors import is_configured
from app.services.data.sources import CSV_INVENTORY, CSV_MARKET, FETCHABLE, OPEN_METEO
from app.services.rbac import P

WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers", 81: "Showers",
    82: "Violent showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def source_ref(src: DataSource | None) -> SourceRef | None:
    return SourceRef(key=src.key, name=src.name, origin=src.origin.value) if src else None


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


def run_out(run: IngestionRun) -> RunOut:
    dur = (run.finished_at - run.started_at).total_seconds() if run.finished_at else None
    return RunOut(
        id=run.id, source=source_ref(run.source), trigger=run.trigger.value, status=run.status.value,
        started_at=run.started_at, finished_at=run.finished_at, duration_seconds=dur,
        rows_received=run.rows_received, rows_inserted=run.rows_inserted, rows_updated=run.rows_updated,
        rows_unchanged=run.rows_unchanged, rows_rejected=run.rows_rejected, warnings=run.warnings,
        error_message=run.error_message, file_name=run.file_name,
        triggered_by=run.triggered_by.full_name if run.triggered_by else None,
        params={k: v for k, v in (run.params or {}).items() if k != "warehouse_ids"},
    )


def run_detail(run: IngestionRun, issues) -> RunDetail:
    return RunDetail(**run_out(run).model_dump(), issues=[
        IssueOut(row_number=i.row_number, field=i.field, severity=i.severity.value, code=i.code,
                 message=i.message, raw=i.raw) for i in issues])


# --------------------------------------------------------------------------- sources


def source_statuses(db: Session, ctx: AuthContext) -> list[SourceStatus]:
    out = []
    for src in db.scalars(select(DataSource).order_by(DataSource.origin, DataSource.name)):
        configured, msg = is_configured(src.key)
        last_run = db.scalars(
            select(IngestionRun).where(IngestionRun.source_id == src.id, IngestionRun.organization_id == ctx.org_id)
            .order_by(IngestionRun.started_at.desc()).limit(1)
        ).first()
        success_q = select(func.max(IngestionRun.finished_at)).where(
            IngestionRun.source_id == src.id, IngestionRun.status.in_([RunStatus.SUCCESS, RunStatus.PARTIAL]))
        if src.origin == SourceOrigin.USER_UPLOAD or src.kind == DataKind.WEATHER:
            success_q = success_q.where(IngestionRun.organization_id == ctx.org_id)
        last_success = db.scalar(success_q)

        count, latest, fresh = 0, None, None
        if src.kind == DataKind.MARKET_PRICES:
            q = select(func.count(), func.max(MarketPrice.arrival_date)).where(
                MarketPrice.source_id == src.id, visible_prices(ctx))
            count, latest_date = db.execute(q).one()
            latest = latest_date.isoformat() if latest_date else None
            fresh = market_freshness(src, latest_date) if latest_date else fr.unavailable(
                "Not configured" if not configured else "No data fetched yet")
        elif src.kind == DataKind.WEATHER:
            scope = [WeatherObservation.source_id == src.id, WeatherObservation.organization_id == ctx.org_id,
                     ctx.warehouse_filter(WeatherObservation.warehouse_id)]
            count = db.scalar(select(func.count()).select_from(WeatherObservation).where(*scope))
            latest_at = db.scalar(select(func.max(WeatherObservation.observed_at)).where(
                *scope, WeatherObservation.kind == WeatherKind.CURRENT))
            latest = latest_at.isoformat() if latest_at else None
            fresh = fr.for_reading(latest_at) if latest_at else fr.unavailable()
        else:
            count = db.scalar(select(func.count()).select_from(IngestionRun).where(
                IngestionRun.source_id == src.id, IngestionRun.organization_id == ctx.org_id)) or 0

        out.append(SourceStatus(
            key=src.key, name=src.name, publisher=src.publisher, kind=src.kind.value, origin=src.origin.value,
            homepage_url=src.homepage_url, license=src.license, update_frequency=src.update_frequency,
            description=src.description, configured=configured, config_message=msg,
            can_run=src.key in FETCHABLE and configured and ctx.has(P.DATA_INGEST),
            can_upload=(src.key == CSV_MARKET and ctx.has(P.DATA_IMPORT))
            or (src.key == CSV_INVENTORY and ctx.has(P.INVENTORY_CREATE) and ctx.has(P.INVENTORY_UPDATE)),
            record_count=count or 0, latest_observation=latest, freshness=fresh,
            last_run=run_out(last_run) if last_run else None, last_success_at=last_success,
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
                                   fetched_at=None,
                                   freshness=fr.unavailable("No market reports for this commodity yet")))
            continue
        sources = {s.id: s for s in db.scalars(select(DataSource).where(
            DataSource.id.in_([sid for sid, _ in per_source])))}
        # Official sources first, then uploads.
        for source_id, latest in sorted(per_source, key=lambda r: sources[r[0]].origin != SourceOrigin.OFFICIAL_API):
            avg, lo, hi, markets, fetched = _stats_on(db, ctx, name, source_id, latest)
            prev_date = db.scalar(select(func.max(MarketPrice.arrival_date)).where(
                visible_prices(ctx), func.lower(MarketPrice.commodity) == name.lower(),
                MarketPrice.source_id == source_id, MarketPrice.arrival_date < latest))
            prev_avg = _stats_on(db, ctx, name, source_id, prev_date)[0] if prev_date else None
            change = round((float(avg) - float(prev_avg)) / float(prev_avg) * 100, 1) if prev_avg else None
            out.append(LatestPrice(
                commodity=name, in_catalog=name.lower() in catalog, source=source_ref(sources[source_id]),
                latest_date=latest, markets_reporting=markets, avg_modal=round(float(avg), 2),
                min_modal=float(lo), max_modal=float(hi), previous_date=prev_date,
                previous_avg_modal=round(float(prev_avg), 2) if prev_avg else None, change_pct=change,
                fetched_at=fetched, freshness=market_freshness(sources[source_id], latest)))
    return out


def price_trend(db: Session, ctx: AuthContext, commodity: str, source_key: str | None,
                markets: list[str], days: int) -> Trend:
    src_q = select(DataSource).join(MarketPrice, MarketPrice.source_id == DataSource.id).where(
        visible_prices(ctx), func.lower(MarketPrice.commodity) == commodity.lower())
    if source_key:
        src_q = src_q.where(DataSource.key == source_key)
    candidates = db.scalars(src_q.distinct()).all()
    if not candidates:
        return Trend(commodity=commodity, source=None, series=[], freshness=fr.unavailable(
            "No market reports for this commodity yet"))
    src = sorted(candidates, key=lambda s: s.origin != SourceOrigin.OFFICIAL_API)[0]
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
    return Trend(commodity=commodity, source=source_ref(src), series=series, freshness=market_freshness(src, latest))


# --------------------------------------------------------------------------- weather


def _weather_source(db) -> DataSource | None:
    return db.scalar(select(DataSource).where(DataSource.key == OPEN_METEO))


def weather_now(db: Session, ctx: AuthContext) -> list[WeatherNow]:
    src = _weather_source(db)
    warehouses = db.scalars(select(Warehouse).where(Warehouse.organization_id == ctx.org_id,
                                                    ctx.warehouse_filter(Warehouse.id))
                            .order_by(Warehouse.name)).unique().all()
    out = []
    for w in warehouses:
        obs = db.scalars(select(WeatherObservation).where(
            WeatherObservation.warehouse_id == w.id, WeatherObservation.kind == WeatherKind.CURRENT)
            .order_by(WeatherObservation.observed_at.desc()).limit(1)).first()
        reading = None
        if obs:
            reading = WeatherReading(observed_at=obs.observed_at, temperature_c=obs.temperature_c,
                                     humidity_pct=obs.humidity_pct, precipitation_mm=obs.precipitation_mm,
                                     wind_kmh=obs.wind_kmh, weather_code=obs.weather_code,
                                     condition=WMO.get(obs.weather_code) if obs.weather_code is not None else None,
                                     fetched_at=obs.fetched_at)
        if w.latitude is None or w.longitude is None:
            fresh = fr.unavailable("Add coordinates to this warehouse to fetch weather")
        else:
            fresh = fr.for_reading(obs.observed_at) if obs else fr.unavailable()
        out.append(WeatherNow(warehouse=Ref(id=w.id, name=w.name), region=Ref(id=w.region.id, name=w.region.name),
                              latitude=w.latitude, longitude=w.longitude, reading=reading, freshness=fresh,
                              source=source_ref(src)))
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


def stale_running(db: Session, source_id, org_id) -> IngestionRun | None:
    """A run for this source/org that is still RUNNING and started in the last 10 minutes."""
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    return db.scalars(select(IngestionRun).where(
        IngestionRun.source_id == source_id, IngestionRun.organization_id == org_id,
        IngestionRun.status == RunStatus.RUNNING, IngestionRun.started_at >= cutoff)).first()

