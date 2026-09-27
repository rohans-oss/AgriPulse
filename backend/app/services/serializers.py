"""Turn ORM rows into response schemas, adding derived fields (usage, scope names)."""

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.models import Commodity, InventoryItem, InventoryMovement, Region, User, Warehouse
from app.models.enums import QuantityUnit, class_for_origin
from app.schemas import (
    CommodityRef,
    InventoryOut,
    MeResponse,
    MovementOut,
    OrganizationOut,
    Ref,
    ScopeOut,
    UserOut,
    WarehouseOut,
    WarehouseRef,
)


def to_tonnes(quantity, unit: QuantityUnit) -> float:
    return float(quantity) * QuantityUnit(unit).tonnes_factor


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        org_wide_access=user.org_wide_access,
        roles=sorted(ra.role.code for ra in user.role_assignments),
        region_ids=[s.region_id for s in user.location_scopes if s.region_id],
        warehouse_ids=[s.warehouse_id for s in user.location_scopes if s.warehouse_id],
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def me_out(db: Session, ctx: AuthContext) -> MeResponse:
    regions = (
        db.scalars(select(Region).where(Region.id.in_(ctx.scoped_region_ids))).all() if ctx.scoped_region_ids else []
    )
    warehouses = (
        db.scalars(select(Warehouse).where(Warehouse.id.in_(ctx.scoped_warehouse_ids))).all()
        if ctx.scoped_warehouse_ids
        else []
    )
    if ctx.allowed_warehouse_ids is None:
        accessible = db.scalar(
            select(func.count()).select_from(Warehouse).where(Warehouse.organization_id == ctx.org_id)
        )
    else:
        accessible = len(ctx.allowed_warehouse_ids)
    return MeResponse(
        user=user_out(ctx.user),
        organization=OrganizationOut.model_validate(ctx.organization),
        roles=sorted(ctx.role_codes),
        primary_role=ctx.primary_role,
        permissions=sorted(ctx.permissions),
        scope=ScopeOut(
            org_wide=ctx.org_wide,
            regions=[Ref(id=r.id, name=r.name) for r in regions],
            warehouses=[Ref(id=w.id, name=w.name) for w in warehouses],
            accessible_warehouse_count=accessible or 0,
        ),
    )


def warehouse_usage(db: Session, org_id: uuid.UUID, warehouse_ids=None) -> dict[uuid.UUID, float]:
    stmt = (
        select(InventoryItem.warehouse_id, Commodity.unit, func.sum(InventoryItem.quantity))
        .join(Commodity, Commodity.id == InventoryItem.commodity_id)
        .where(InventoryItem.organization_id == org_id)
        .group_by(InventoryItem.warehouse_id, Commodity.unit)
    )
    if warehouse_ids is not None:
        stmt = stmt.where(InventoryItem.warehouse_id.in_(warehouse_ids))
    usage: dict[uuid.UUID, float] = defaultdict(float)
    for wid, unit, qty in db.execute(stmt):
        usage[wid] += to_tonnes(qty or 0, unit)
    return usage


def warehouse_out(w: Warehouse, used_tonnes: float = 0.0) -> WarehouseOut:
    capacity = float(w.capacity_tonnes)
    return WarehouseOut(
        id=w.id,
        name=w.name,
        region=Ref(id=w.region.id, name=w.region.name),
        address=w.address,
        latitude=w.latitude,
        longitude=w.longitude,
        capacity_tonnes=capacity,
        used_tonnes=round(used_tonnes, 3),
        utilization_pct=round(used_tonnes / capacity * 100, 1) if capacity else 0.0,
        storage_type=w.storage_type,
        status=w.status,
        data_origin=w.data_origin,
        data_class=class_for_origin(w.data_origin),
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


def inventory_out(item: InventoryItem) -> InventoryOut:
    c, w = item.commodity, item.warehouse
    return InventoryOut(
        id=item.id,
        warehouse=WarehouseRef(id=w.id, name=w.name, region_id=w.region_id),
        commodity=CommodityRef(id=c.id, name=c.name, unit=c.unit, category=c.category),
        quantity=float(item.quantity),
        unit=c.unit,
        quantity_tonnes=round(to_tonnes(item.quantity, c.unit), 3),
        notes=item.notes,
        data_origin=item.data_origin,
        data_class=class_for_origin(item.data_origin),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def movement_out(m: InventoryMovement) -> MovementOut:
    return MovementOut(
        id=m.id,
        warehouse=Ref(id=m.warehouse.id, name=m.warehouse.name),
        commodity=Ref(id=m.commodity.id, name=m.commodity.name),
        movement_type=m.movement_type,
        quantity_delta=float(m.quantity_delta),
        quantity_after=float(m.quantity_after),
        reason=m.reason,
        data_origin=m.data_origin,
        data_class=class_for_origin(m.data_origin),
        created_at=m.created_at,
    )
