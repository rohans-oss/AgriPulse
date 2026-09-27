import uuid
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require
from app.api.routes.warehouses import get_accessible_warehouse
from app.core.config import get_settings
from app.core.database import get_db, get_session_factory
from app.models import DataSource, IngestionIssue, IngestionRun, MarketPrice, OrganizationSourceSetting
from app.models.enums import RunTrigger, ValidationStatus
from app.schemas.data import (
    FilterCommodity,
    ImportResult,
    LatestPrice,
    MarketFilters,
    PricePage,
    RunDetail,
    RunOut,
    SourceStatus,
    Compare,
    DataEnvironment,
    PriceDetail,
    SourceSettingsUpdate,
    Trend,
    WeatherHistory,
    WeatherNow,
)
from app.services.audit import record_audit
from app.services.data import connectors, imports, queries
from app.services.data.freshness import today_ist
from app.services.data.scheduler import auto_refresh_enabled
from app.services.data.sources import FETCHABLE, OGD_MANDI, OPEN_METEO
from app.services.rbac import P

data_router = APIRouter(prefix="/data", tags=["data platform"])
market_router = APIRouter(prefix="/market", tags=["market prices"])
weather_router = APIRouter(prefix="/weather", tags=["weather"])
imports_router = APIRouter(prefix="/imports", tags=["imports"])


# --------------------------------------------------------------------------- sources & runs


@data_router.get("/sources", response_model=list[SourceStatus])
def list_sources(ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    return queries.source_statuses(db, ctx)


@data_router.post("/sources/{key}/runs", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def start_run(key: str, request: Request, background: BackgroundTasks,
              ctx: AuthContext = Depends(require(P.DATA_INGEST)), db: Session = Depends(get_db),
              session_factory=Depends(get_session_factory)):
    src = db.scalar(select(DataSource).where(DataSource.key == key))
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found")
    if key not in FETCHABLE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This source is filled by uploading a file")
    if not src.is_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "This source is disabled")
    ok, msg = connectors.is_configured(key)
    if not ok:
        raise HTTPException(status.HTTP_409_CONFLICT, msg)
    # Mandi prices are one shared public dataset: the run is public (organization_id NULL) so every
    # workspace sees the same fetch history. Weather is fetched per organization.
    run_org = None if key == OGD_MANDI else ctx.org_id
    if queries.stale_running(db, src.id, run_org):
        raise HTTPException(status.HTTP_409_CONFLICT, "A fetch for this source is already running")
    params: dict = {}
    if key == OPEN_METEO and ctx.allowed_warehouse_ids is not None:
        params["warehouse_ids"] = [str(w) for w in ctx.allowed_warehouse_ids]
    run = IngestionRun(source_id=src.id, organization_id=run_org, triggered_by_id=ctx.user.id,
                       trigger=RunTrigger.MANUAL, params=params)
    db.add(run)
    db.flush()
    record_audit(db, action="data.ingest", entity_type="ingestion_run", entity_id=run.id, organization_id=ctx.org_id,
                 actor_user_id=ctx.user.id, details={"source": key}, request=request)
    db.commit()
    db.refresh(run)
    background.add_task(connectors.execute_run, session_factory, run.id)
    return queries.run_out(run, ctx)


def _fetchable_source(db: Session, key: str) -> DataSource:
    src = db.scalar(select(DataSource).where(DataSource.key == key))
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data source not found")
    if key not in FETCHABLE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This source is filled by uploading a file")
    return src


@data_router.get("/sources/{key}/settings", response_model=SourceSettingsUpdate)
def get_source_settings(key: str, ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    _fetchable_source(db, key)
    return SourceSettingsUpdate(auto_refresh=auto_refresh_enabled(db, ctx.org_id, key))


@data_router.patch("/sources/{key}/settings", response_model=SourceSettingsUpdate)
def update_source_settings(key: str, body: SourceSettingsUpdate, request: Request,
                           ctx: AuthContext = Depends(require(P.DATA_INGEST)), db: Session = Depends(get_db)):
    """Per-organization: switch automatic refresh on/off for this workspace only."""
    _fetchable_source(db, key)
    row = db.scalar(select(OrganizationSourceSetting).where(
        OrganizationSourceSetting.organization_id == ctx.org_id, OrganizationSourceSetting.source_key == key))
    if row is None:
        row = OrganizationSourceSetting(organization_id=ctx.org_id, source_key=key)
        db.add(row)
    row.auto_refresh = body.auto_refresh
    row.updated_by_id = ctx.user.id
    record_audit(db, action="data.source_settings", entity_type="data_source", entity_id=None,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id,
                 details={"source": key, "auto_refresh": body.auto_refresh}, request=request)
    db.commit()
    return SourceSettingsUpdate(auto_refresh=row.auto_refresh)


@data_router.get("/environment", response_model=DataEnvironment)
def data_environment(ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    return queries.environment(db, ctx)


@data_router.get("/runs", response_model=list[RunOut])
def list_runs(source: str | None = None, limit: int = Query(30, ge=1, le=200),
              ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    stmt = (select(IngestionRun).where(queries.visible_runs(ctx))
            .order_by(IngestionRun.started_at.desc()).limit(limit))
    if source:
        stmt = stmt.join(DataSource, DataSource.id == IngestionRun.source_id).where(DataSource.key == source)
    return [queries.run_out(r, ctx) for r in db.scalars(stmt).unique()]


@data_router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: uuid.UUID, ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    run = db.get(IngestionRun, run_id)
    if run is None or (run.organization_id is not None and run.organization_id != ctx.org_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    issues = db.scalars(select(IngestionIssue).where(IngestionIssue.run_id == run.id)
                        .order_by(IngestionIssue.severity, IngestionIssue.row_number).limit(500)).all()
    return queries.run_detail(run, issues, ctx)


# --------------------------------------------------------------------------- market


@market_router.get("/filters", response_model=MarketFilters)
def market_filters(ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    vis = queries.visible_prices(ctx)

    def distinct(col):
        return [v for v in db.scalars(select(col).where(vis, col != "").distinct().order_by(col)) if v]

    catalog = {n.lower() for n in queries.catalog_names(db, ctx)}
    comms = db.execute(select(MarketPrice.commodity, func.count(), func.max(MarketPrice.arrival_date))
                       .where(vis).group_by(MarketPrice.commodity).order_by(MarketPrice.commodity)).all()
    srcs = db.scalars(select(DataSource).join(MarketPrice, MarketPrice.source_id == DataSource.id)
                      .where(vis).distinct()).all()
    return MarketFilters(
        states=distinct(MarketPrice.state), districts=distinct(MarketPrice.district),
        markets=distinct(MarketPrice.market),
        commodities=[FilterCommodity(name=c, rows=n, latest_date=d, in_catalog=c.lower() in catalog)
                     for c, n, d in comms],
        sources=[queries.source_ref(s) for s in srcs],
    )


@market_router.get("/prices", response_model=PricePage)
def market_prices(
    commodity: str | None = None, state: str | None = None, district: str | None = None,
    market: str | None = None, source: str | None = None,
    validation: ValidationStatus | None = None, freshness: str | None = Query(None, pattern="^(DAILY|HISTORICAL)$"),
    date_from: date | None = None, date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
    ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db),
):
    conds = [queries.visible_prices(ctx)]
    if commodity:
        conds.append(func.lower(MarketPrice.commodity) == commodity.lower())
    if state:
        conds.append(MarketPrice.state == state)
    if district:
        conds.append(MarketPrice.district == district)
    if market:
        conds.append(MarketPrice.market == market)
    if source:
        conds.append(MarketPrice.source_id.in_(select(DataSource.id).where(DataSource.key == source)))
    if validation:
        conds.append(MarketPrice.validation_status == validation)
    if freshness:
        # DAILY = reported today or yesterday (IST), HISTORICAL = older.
        cutoff = today_ist() - timedelta(days=1)
        conds.append(MarketPrice.arrival_date >= cutoff if freshness == "DAILY" else MarketPrice.arrival_date < cutoff)
    if date_from:
        conds.append(MarketPrice.arrival_date >= date_from)
    if date_to:
        conds.append(MarketPrice.arrival_date <= date_to)
    total = db.scalar(select(func.count()).select_from(MarketPrice).where(*conds)) or 0
    rows = db.scalars(select(MarketPrice).where(*conds)
                      .order_by(MarketPrice.arrival_date.desc(), MarketPrice.commodity, MarketPrice.market)
                      .limit(limit).offset(offset)).unique()
    return PricePage(total=total, rows=[queries.price_out(r) for r in rows])


@market_router.get("/prices/{price_id}", response_model=PriceDetail)
def market_price_detail(price_id: uuid.UUID, ctx: AuthContext = Depends(require(P.DATA_READ)),
                        db: Session = Depends(get_db)):
    r = db.get(MarketPrice, price_id)
    if r is None or (r.organization_id is not None and r.organization_id != ctx.org_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Price not found")
    return queries.price_detail(db, ctx, r)


@market_router.get("/compare", response_model=Compare)
def market_compare(commodity: str, by: str = Query("market", pattern="^(market|district|state)$"),
                   days: int = Query(7, ge=1, le=90), source: str | None = None,
                   ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    return queries.compare(db, ctx, commodity, by, days, source)


@market_router.get("/latest", response_model=list[LatestPrice])
def market_latest(commodity: list[str] | None = Query(None),
                  ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    return queries.latest_prices(db, ctx, commodity)


@market_router.get("/trend", response_model=Trend)
def market_trend(commodity: str, source: str | None = None, market: list[str] | None = Query(None),
                 days: int = Query(90, ge=7, le=730),
                 ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    return queries.price_trend(db, ctx, commodity, source, market or [], days)


# --------------------------------------------------------------------------- weather


@weather_router.get("/current", response_model=list[WeatherNow])
def weather_current(region_id: uuid.UUID | None = None, warehouse_id: uuid.UUID | None = None,
                    ctx: AuthContext = Depends(require(P.DATA_READ, P.WAREHOUSE_READ)), db: Session = Depends(get_db)):
    if warehouse_id:
        get_accessible_warehouse(db, ctx, warehouse_id)  # 404 other org, 403 out of scope
    return queries.weather_now(db, ctx, region_id=region_id, warehouse_id=warehouse_id)


@weather_router.get("/daily", response_model=WeatherHistory)
def weather_daily(warehouse_id: uuid.UUID, days: int = Query(14, ge=1, le=92),
                  ctx: AuthContext = Depends(require(P.DATA_READ, P.WAREHOUSE_READ)), db: Session = Depends(get_db)):
    wh = get_accessible_warehouse(db, ctx, warehouse_id)
    return queries.weather_history(db, ctx, wh, days)


# --------------------------------------------------------------------------- imports


async def _read(file: UploadFile) -> tuple[str, bytes]:
    limit = get_settings().max_upload_bytes
    content = await file.read(limit + 1)
    name = (file.filename or "upload.csv").rsplit("/", 1)[-1][:255]
    if not name.lower().endswith((".csv", ".txt")):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a .csv file")
    return name, content


@imports_router.post("/market-prices", response_model=ImportResult)
async def upload_market_prices(request: Request, file: UploadFile = File(...), dry_run: bool = True,
                               ctx: AuthContext = Depends(require(P.DATA_IMPORT)), db: Session = Depends(get_db)):
    name, content = await _read(file)
    return imports.import_market_prices(db, ctx, name, content, dry_run, get_settings().max_upload_bytes, request)


@imports_router.post("/inventory", response_model=ImportResult)
async def upload_inventory(request: Request, file: UploadFile = File(...), dry_run: bool = True,
                           ctx: AuthContext = Depends(require(P.INVENTORY_CREATE, P.INVENTORY_UPDATE)),
                           db: Session = Depends(get_db)):
    name, content = await _read(file)
    return imports.import_inventory(db, ctx, name, content, dry_run, get_settings().max_upload_bytes, request)
