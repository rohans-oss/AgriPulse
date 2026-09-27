"""Role-specific dashboard, computed server-side from the caller's role and scope.

Each role gets a different set of KPIs and sections. Every figure is derived
from the database rows the caller is allowed to see; nothing is hard-coded.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.core.database import get_db
from app.models import Commodity, InventoryItem, InventoryMovement, Region, User, Warehouse
from app.models.enums import MovementType, RecordStatus, RoleCode, StorageType
from app.schemas import InventoryOut, MovementOut, OrganizationOut, WarehouseOut
from app.schemas.data import LatestPrice, SourceStatus, WeatherNow
from app.services.data import queries as data_queries
from app.services.rbac import P
from app.services.serializers import inventory_out, movement_out, to_tonnes, warehouse_out, warehouse_usage

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

NEAR_CAPACITY_PCT = 85.0


class Kpi(BaseModel):
    key: str
    label: str
    value: float | int | str
    unit: str | None = None
    hint: str | None = None
    tone: str = "neutral"  # neutral | good | warn | bad


class CommodityTotal(BaseModel):
    commodity_id: str
    name: str
    category: str
    quantity_tonnes: float
    warehouse_count: int


class RegionTotal(BaseModel):
    region_id: str
    name: str
    state: str
    quantity_tonnes: float
    warehouse_count: int
    capacity_tonnes: float


class MovementSummary(BaseModel):
    days: int
    inbound_tonnes: float
    outbound_tonnes: float
    inbound_count: int
    outbound_count: int


class DailyMovement(BaseModel):
    day: date
    inbound_tonnes: float
    outbound_tonnes: float


class OrgSummary(BaseModel):
    organization: OrganizationOut
    active_users: int
    total_users: int
    users_by_role: dict[str, int]


class DashboardOut(BaseModel):
    role: str | None
    title: str
    subtitle: str
    scope_label: str
    is_synthetic: bool
    generated_at: datetime
    kpis: list[Kpi]
    organization: OrgSummary | None = None
    warehouses: list[WarehouseOut] | None = None
    inventory_by_commodity: list[CommodityTotal] | None = None
    inventory_by_region: list[RegionTotal] | None = None
    inventory_items: list[InventoryOut] | None = None
    movement_summary: MovementSummary | None = None
    daily_movements: list[DailyMovement] | None = None
    recent_movements: list[MovementOut] | None = None
    # V2 — real external data (always carries its own source and freshness)
    market: list[LatestPrice] | None = None
    weather: list[WeatherNow] | None = None
    data_sources: list[SourceStatus] | None = None


TITLES = {
    RoleCode.ORGANIZATION_ADMIN.value: ("Organization Overview", "Workspace, people and master data at a glance"),
    RoleCode.OPERATIONS_MANAGER.value: ("Operations Control Center", "Stock, capacity and activity across your network"),
    RoleCode.PROCUREMENT_MANAGER.value: ("Procurement Overview", "Current stock available across warehouses"),
    RoleCode.WAREHOUSE_MANAGER.value: ("Warehouse Operations", "Capacity, stock and movements for your warehouses"),
    RoleCode.LOGISTICS_MANAGER.value: ("Logistics Overview", "Where stock sits across locations and regions"),
    RoleCode.ANALYST.value: ("Analytics", "Inventory distribution and recorded history"),
    RoleCode.VIEWER.value: ("AgriFlow Overview", "Read-only summary of approved data"),
}


class _Data:
    """Scoped data loaded once and shared by the section builders."""

    def __init__(self, db: Session, ctx: AuthContext):
        self.db, self.ctx = db, ctx
        self.warehouses = db.scalars(
            select(Warehouse).where(Warehouse.organization_id == ctx.org_id, ctx.warehouse_filter(Warehouse.id))
            .order_by(Warehouse.name)
        ).unique().all()
        self.usage = warehouse_usage(db, ctx.org_id, [w.id for w in self.warehouses])
        self.items = db.scalars(
            select(InventoryItem).where(InventoryItem.organization_id == ctx.org_id,
                                        ctx.warehouse_filter(InventoryItem.warehouse_id))
        ).unique().all()
        self.regions = db.scalars(select(Region).where(Region.organization_id == ctx.org_id).order_by(Region.name)).all()
        self.commodities = db.scalars(select(Commodity).where(Commodity.organization_id == ctx.org_id)).all()

    # -- aggregates
    @property
    def total_tonnes(self) -> float:
        return round(sum(self.usage.values()), 3)

    @property
    def total_capacity(self) -> float:
        return round(sum(float(w.capacity_tonnes) for w in self.warehouses), 3)

    @property
    def utilization(self) -> float:
        return round(self.total_tonnes / self.total_capacity * 100, 1) if self.total_capacity else 0.0

    def warehouse_rows(self) -> list[WarehouseOut]:
        return [warehouse_out(w, self.usage.get(w.id, 0.0)) for w in self.warehouses]

    def near_capacity(self) -> int:
        return sum(1 for w in self.warehouse_rows() if w.utilization_pct >= NEAR_CAPACITY_PCT)

    def by_commodity(self) -> list[CommodityTotal]:
        acc: dict = defaultdict(lambda: [0.0, set()])
        for i in self.items:
            acc[i.commodity_id][0] += to_tonnes(i.quantity, i.commodity.unit)
            if i.quantity > 0:
                acc[i.commodity_id][1].add(i.warehouse_id)
        by_id = {c.id: c for c in self.commodities}
        rows = [CommodityTotal(commodity_id=str(cid), name=by_id[cid].name, category=by_id[cid].category.value,
                               quantity_tonnes=round(t, 3), warehouse_count=len(ws)) for cid, (t, ws) in acc.items()]
        return sorted(rows, key=lambda r: -r.quantity_tonnes)

    def by_region(self) -> list[RegionTotal]:
        rows = []
        for r in self.regions:
            ws = [w for w in self.warehouses if w.region_id == r.id]
            if not ws and not self.ctx.org_wide:
                continue
            rows.append(RegionTotal(
                region_id=str(r.id), name=r.name, state=r.state,
                quantity_tonnes=round(sum(self.usage.get(w.id, 0.0) for w in ws), 3),
                warehouse_count=len(ws), capacity_tonnes=round(sum(float(w.capacity_tonnes) for w in ws), 3),
            ))
        return sorted(rows, key=lambda r: -r.quantity_tonnes)

    def _movements_since(self, since: datetime):
        return self.db.scalars(
            select(InventoryMovement).where(
                InventoryMovement.organization_id == self.ctx.org_id,
                self.ctx.warehouse_filter(InventoryMovement.warehouse_id),
                InventoryMovement.created_at >= since,
            )
        ).unique().all()

    def movement_summary(self, days: int) -> MovementSummary:
        # Only real adjustments count as flow; opening balances (INITIAL) and record
        # removals (REMOVAL) are bookkeeping events, not goods moving in or out.
        s = MovementSummary(days=days, inbound_tonnes=0, outbound_tonnes=0, inbound_count=0, outbound_count=0)
        for m in self._movements_since(datetime.now(UTC) - timedelta(days=days)):
            t = to_tonnes(m.quantity_delta, m.commodity.unit)
            if m.movement_type == MovementType.INBOUND:
                s.inbound_tonnes += t
                s.inbound_count += 1
            elif m.movement_type == MovementType.OUTBOUND:
                s.outbound_tonnes += -t
                s.outbound_count += 1
        s.inbound_tonnes, s.outbound_tonnes = round(s.inbound_tonnes, 3), round(s.outbound_tonnes, 3)
        return s

    def daily(self, days: int) -> list[DailyMovement]:
        today = datetime.now(UTC).date()
        buckets = {today - timedelta(days=d): [0.0, 0.0] for d in range(days - 1, -1, -1)}
        for m in self._movements_since(datetime.now(UTC) - timedelta(days=days)):
            day = m.created_at.astimezone(UTC).date() if m.created_at.tzinfo else m.created_at.date()
            if day not in buckets or m.movement_type not in (MovementType.INBOUND, MovementType.OUTBOUND):
                continue
            t = to_tonnes(m.quantity_delta, m.commodity.unit)
            if t >= 0:
                buckets[day][0] += t
            else:
                buckets[day][1] += -t
        return [DailyMovement(day=d, inbound_tonnes=round(i, 3), outbound_tonnes=round(o, 3))
                for d, (i, o) in buckets.items()]

    def recent(self, limit: int = 10) -> list[MovementOut]:
        rows = self.db.scalars(
            select(InventoryMovement).where(InventoryMovement.organization_id == self.ctx.org_id,
                                            self.ctx.warehouse_filter(InventoryMovement.warehouse_id))
            .order_by(InventoryMovement.created_at.desc()).limit(limit)
        ).unique().all()
        return [movement_out(m) for m in rows]

    def item_rows(self) -> list[InventoryOut]:
        return [inventory_out(i) for i in sorted(self.items, key=lambda i: (i.warehouse.name, i.commodity.name))]


def _kpi(key, label, value, unit=None, hint=None, tone="neutral") -> Kpi:
    return Kpi(key=key, label=label, value=value, unit=unit, hint=hint, tone=tone)


def _util_tone(pct: float) -> str:
    return "bad" if pct >= 95 else "warn" if pct >= NEAR_CAPACITY_PCT else "good"


@router.get("", response_model=DashboardOut)
def get_dashboard(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    d = _Data(db, ctx)
    role = ctx.primary_role
    title, subtitle = TITLES.get(role, ("Dashboard", ""))
    if ctx.org_wide:
        scope_label = "All locations"
    else:
        names = sorted([w.name for w in d.warehouses])
        scope_label = ", ".join(names) if 0 < len(names) <= 3 else f"{len(names)} assigned warehouses"
    out = DashboardOut(role=role, title=title, subtitle=subtitle, scope_label=scope_label,
                       is_synthetic=ctx.organization.is_demo, generated_at=datetime.now(UTC), kpis=[])
    active_commodities = sum(1 for c in d.commodities if c.status == RecordStatus.ACTIVE)
    stocked_commodities = sum(1 for r in d.by_commodity() if r.quantity_tonnes > 0)

    if role == RoleCode.ORGANIZATION_ADMIN.value:
        users = db.scalars(select(User).where(User.organization_id == ctx.org_id)).all()
        by_role: dict[str, int] = defaultdict(int)
        for u in users:
            for ra in u.role_assignments:
                by_role[ra.role.code] += 1
        out.organization = OrgSummary(organization=OrganizationOut.model_validate(ctx.organization),
                                      active_users=sum(u.is_active for u in users), total_users=len(users),
                                      users_by_role=dict(by_role))
        out.kpis = [
            _kpi("users", "Users", len(users), hint=f"{out.organization.active_users} active"),
            _kpi("warehouses", "Warehouses", len(d.warehouses)),
            _kpi("commodities", "Commodities", len(d.commodities), hint=f"{active_commodities} active"),
            _kpi("inventory", "Total inventory", d.total_tonnes, "t"),
            _kpi("regions", "Regions", len(d.regions)),
        ]
        out.warehouses = d.warehouse_rows()
        out.inventory_by_commodity = d.by_commodity()
        out.inventory_by_region = d.by_region()

    elif role == RoleCode.OPERATIONS_MANAGER.value:
        near = d.near_capacity()
        out.kpis = [
            _kpi("inventory", "Total inventory", d.total_tonnes, "t"),
            _kpi("utilization", "Network utilization", d.utilization, "%", f"of {d.total_capacity:,.0f} t capacity",
                 _util_tone(d.utilization)),
            _kpi("warehouses", "Warehouses", len(d.warehouses)),
            _kpi("near_capacity", "Near capacity", near, hint=f"≥ {NEAR_CAPACITY_PCT:.0f}% full",
                 tone="warn" if near else "good"),
            _kpi("commodities", "Commodities in stock", stocked_commodities),
        ]
        out.warehouses = d.warehouse_rows()
        out.inventory_by_commodity = d.by_commodity()
        out.inventory_by_region = d.by_region()
        out.movement_summary = d.movement_summary(7)

    elif role == RoleCode.PROCUREMENT_MANAGER.value:
        out.kpis = [
            _kpi("inventory", "Current inventory", d.total_tonnes, "t"),
            _kpi("commodities", "Available commodities", stocked_commodities, hint=f"{active_commodities} active in catalog"),
            _kpi("warehouses", "Warehouses holding stock", sum(1 for w in d.warehouses if d.usage.get(w.id, 0) > 0)),
        ]
        out.inventory_by_commodity = d.by_commodity()
        out.inventory_items = d.item_rows()
        out.warehouses = d.warehouse_rows()

    elif role == RoleCode.WAREHOUSE_MANAGER.value:
        summary = d.movement_summary(7)
        out.kpis = [
            _kpi("assigned", "Assigned warehouses", len(d.warehouses)),
            _kpi("capacity", "Capacity", d.total_capacity, "t"),
            _kpi("stock", "In stock", d.total_tonnes, "t"),
            _kpi("utilization", "Utilization", d.utilization, "%", tone=_util_tone(d.utilization)),
            _kpi("inbound", "Inbound (7 days)", summary.inbound_tonnes, "t", f"{summary.inbound_count} movements"),
            _kpi("outbound", "Outbound (7 days)", summary.outbound_tonnes, "t", f"{summary.outbound_count} movements"),
        ]
        out.warehouses = d.warehouse_rows()
        out.inventory_items = d.item_rows()
        out.movement_summary = summary
        out.recent_movements = d.recent(10)

    elif role == RoleCode.LOGISTICS_MANAGER.value:
        regions_covered = len({w.region_id for w in d.warehouses})
        out.kpis = [
            _kpi("warehouses", "Warehouse locations", len(d.warehouses)),
            _kpi("regions", "Regions covered", regions_covered),
            _kpi("stock", "Stock to move from", d.total_tonnes, "t"),
            _kpi("cold", "Cold-storage sites",
                 sum(1 for w in d.warehouses if w.storage_type == StorageType.COLD_STORAGE)),
        ]
        out.warehouses = d.warehouse_rows()
        out.inventory_by_region = d.by_region()
        out.inventory_items = d.item_rows()

    elif role == RoleCode.ANALYST.value:
        summary30 = d.movement_summary(30)
        out.kpis = [
            _kpi("inventory", "Total inventory", d.total_tonnes, "t"),
            _kpi("commodities", "Commodities tracked", len(d.commodities)),
            _kpi("regions", "Regions", len(d.by_region())),
            _kpi("movements", "Movements (30 days)", summary30.inbound_count + summary30.outbound_count),
        ]
        out.inventory_by_commodity = d.by_commodity()
        out.inventory_by_region = d.by_region()
        out.warehouses = d.warehouse_rows()
        out.movement_summary = summary30
        out.daily_movements = d.daily(14)

    else:  # VIEWER and any role without a dedicated layout
        out.kpis = [
            _kpi("inventory", "Total inventory", d.total_tonnes, "t"),
            _kpi("warehouses", "Warehouses", len(d.warehouses)),
            _kpi("commodities", "Commodities in stock", stocked_commodities),
            _kpi("utilization", "Utilization", d.utilization, "%", tone=_util_tone(d.utilization)),
        ]
        if ctx.has(P.INVENTORY_READ):
            out.inventory_by_commodity = d.by_commodity()
        if ctx.has(P.WAREHOUSE_READ):
            out.warehouses = d.warehouse_rows()

    _add_external(db, ctx, out, role)
    return out


# Which external-data blocks each role's dashboard shows.
EXTERNAL = {
    RoleCode.ORGANIZATION_ADMIN.value: {"sources", "market"},
    RoleCode.OPERATIONS_MANAGER.value: {"market", "weather"},
    RoleCode.PROCUREMENT_MANAGER.value: {"market"},
    RoleCode.WAREHOUSE_MANAGER.value: {"weather"},
    RoleCode.LOGISTICS_MANAGER.value: {"weather"},
    RoleCode.ANALYST.value: {"market", "sources"},
    RoleCode.VIEWER.value: {"market"},
}


def _add_external(db: Session, ctx: AuthContext, out: DashboardOut, role: str | None) -> None:
    if not ctx.has(P.DATA_READ):
        return
    blocks = EXTERNAL.get(role or "", set())
    if "market" in blocks:
        out.market = data_queries.latest_prices(db, ctx)
    if "weather" in blocks and ctx.has(P.WAREHOUSE_READ):
        out.weather = data_queries.weather_now(db, ctx)
    if "sources" in blocks:
        out.data_sources = data_queries.source_statuses(db, ctx)
