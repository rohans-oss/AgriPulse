import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import get_owned
from app.api.deps import AuthContext, require
from app.api.routes.warehouses import get_accessible_warehouse
from app.core.config import get_settings
from app.core.database import get_db, get_session_factory
from app.models import DataSource, IngestionIssue, IngestionRun, MarketPrice
from app.models.enums import RunTrigger
from app.schemas.data import (
    FilterCommodity,
    ImportResult,
    LatestPrice,
    MarketFilters,
    PriceOut,
    PricePage,
    RunDetail,
    RunOut,
    SourceStatus,
    Trend,
    WeatherHistory,
    WeatherNow,
)
from app.services.audit import record_audit
from app.services.data import connectors, imports, queries
from app.services.data.sources import FETCHABLE, OPEN_METEO
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
    if queries.stale_running(db, src.id, ctx.org_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A fetch for this source is already running")
    params: dict = {}
    if key == OPEN_METEO and ctx.allowed_warehouse_ids is not None:
        params["warehouse_ids"] = [str(w) for w in ctx.allowed_warehouse_ids]
    run = IngestionRun(source_id=src.id, organization_id=ctx.org_id, triggered_by_id=ctx.user.id,
                       trigger=RunTrigger.MANUAL, params=params)
    db.add(run)
    db.flush()
    record_audit(db, action="data.ingest", entity_type="ingestion_run", entity_id=run.id, organization_id=ctx.org_id,
                 actor_user_id=ctx.user.id, details={"source": key}, request=request)
    db.commit()
    db.refresh(run)
    background.add_task(connectors.execute_run, session_factory, run.id)
    return queries.run_out(run)


@data_router.get("/runs", response_model=list[RunOut])
def list_runs(source: str | None = None, limit: int = Query(30, ge=1, le=200),
              ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    stmt = (select(IngestionRun).where(IngestionRun.organization_id == ctx.org_id)
            .order_by(IngestionRun.started_at.desc()).limit(limit))
    if source:
        stmt = stmt.join(DataSource, DataSource.id == IngestionRun.source_id).where(DataSource.key == source)
    return [queries.run_out(r) for r in db.scalars(stmt).unique()]


@data_router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: uuid.UUID, ctx: AuthContext = Depends(require(P.DATA_READ)), db: Session = Depends(get_db)):
    run = get_owned(db, IngestionRun, run_id, ctx.org_id, "Run")
    issues = db.scalars(select(IngestionIssue).where(IngestionIssue.run_id == run.id)
                        .order_by(IngestionIssue.severity, IngestionIssue.row_number).limit(500)).all()
    return queries.run_detail(run, issues)


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
    if date_from:
        conds.append(MarketPrice.arrival_date >= date_from)
    if date_to:
        conds.append(MarketPrice.arrival_date <= date_to)
    total = db.scalar(select(func.count()).select_from(MarketPrice).where(*conds)) or 0
    rows = db.scalars(select(MarketPrice).where(*conds)
                      .order_by(MarketPrice.arrival_date.desc(), MarketPrice.commodity, MarketPrice.market)
                      .limit(limit).offset(offset)).unique()
    return PricePage(total=total, rows=[PriceOut(
        id=r.id, state=r.state, district=r.district, market=r.market, commodity=r.commodity, variety=r.variety,
        grade=r.grade, arrival_date=r.arrival_date, min_price=float(r.min_price) if r.min_price is not None else None,
        max_price=float(r.max_price) if r.max_price is not None else None, modal_price=float(r.modal_price),
        source=queries.source_ref(r.source), fetched_at=r.fetched_at) for r in rows])


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
def weather_current(ctx: AuthContext = Depends(require(P.DATA_READ, P.WAREHOUSE_READ)), db: Session = Depends(get_db)):
    return queries.weather_now(db, ctx)


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
