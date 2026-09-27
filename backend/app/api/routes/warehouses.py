import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import apply_updates, commit_or_conflict, flush_or_conflict, get_owned
from app.api.deps import AuthContext, require
from app.core.database import get_db
from app.models import InventoryItem, Region, Warehouse
from app.models.enums import DataOrigin, StorageType, WarehouseStatus
from app.schemas import WarehouseCreate, WarehouseOut, WarehouseUpdate
from app.services.audit import record_audit
from app.services.rbac import P
from app.services.serializers import warehouse_out, warehouse_usage

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


def get_accessible_warehouse(db: Session, ctx: AuthContext, warehouse_id: uuid.UUID) -> Warehouse:
    """Org check (404) then location-scope check (403)."""
    warehouse = get_owned(db, Warehouse, warehouse_id, ctx.org_id, "Warehouse")
    if not ctx.can_access_warehouse(warehouse.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this warehouse")
    return warehouse


def _region_for_write(db: Session, ctx: AuthContext, region_id: uuid.UUID) -> Region:
    region = db.get(Region, region_id)
    if region is None or region.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Region not found in this organization")
    if not ctx.can_manage_in_region(region.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Region is outside your location scope")
    return region


@router.get("", response_model=list[WarehouseOut])
def list_warehouses(
    region_id: uuid.UUID | None = None,
    storage_type: StorageType | None = None,
    status_filter: WarehouseStatus | None = Query(None, alias="status"),
    ctx: AuthContext = Depends(require(P.WAREHOUSE_READ)),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Warehouse)
        .where(Warehouse.organization_id == ctx.org_id, ctx.warehouse_filter(Warehouse.id))
        .order_by(Warehouse.name)
    )
    if region_id:
        stmt = stmt.where(Warehouse.region_id == region_id)
    if storage_type:
        stmt = stmt.where(Warehouse.storage_type == storage_type)
    if status_filter:
        stmt = stmt.where(Warehouse.status == status_filter)
    warehouses = db.scalars(stmt).all()
    usage = warehouse_usage(db, ctx.org_id, [w.id for w in warehouses])
    return [warehouse_out(w, usage.get(w.id, 0.0)) for w in warehouses]


@router.get("/{warehouse_id}", response_model=WarehouseOut)
def get_warehouse(warehouse_id: uuid.UUID, ctx: AuthContext = Depends(require(P.WAREHOUSE_READ)),
                  db: Session = Depends(get_db)):
    w = get_accessible_warehouse(db, ctx, warehouse_id)
    return warehouse_out(w, warehouse_usage(db, ctx.org_id, [w.id]).get(w.id, 0.0))


@router.post("", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(body: WarehouseCreate, request: Request,
                     ctx: AuthContext = Depends(require(P.WAREHOUSE_MANAGE)), db: Session = Depends(get_db)):
    _region_for_write(db, ctx, body.region_id)
    warehouse = Warehouse(organization_id=ctx.org_id, **body.model_dump())
    db.add(warehouse)
    flush_or_conflict(db, "A warehouse with this name already exists")
    record_audit(db, action="warehouse.create", entity_type="warehouse", entity_id=warehouse.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id,
                 details={"name": warehouse.name, "capacity_tonnes": str(warehouse.capacity_tonnes)},
                 request=request)
    db.commit()
    db.refresh(warehouse)
    return warehouse_out(warehouse)


@router.patch("/{warehouse_id}", response_model=WarehouseOut)
def update_warehouse(warehouse_id: uuid.UUID, body: WarehouseUpdate, request: Request,
                     ctx: AuthContext = Depends(require(P.WAREHOUSE_MANAGE)), db: Session = Depends(get_db)):
    warehouse = get_accessible_warehouse(db, ctx, warehouse_id)
    updates = body.model_dump(exclude_unset=True)
    if updates.get("region_id") and updates["region_id"] != warehouse.region_id:
        _region_for_write(db, ctx, updates["region_id"])
    used = warehouse_usage(db, ctx.org_id, [warehouse.id]).get(warehouse.id, 0.0)
    if "capacity_tonnes" in updates and float(updates["capacity_tonnes"]) < used:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Capacity cannot be below current stock ({used:.3f} t)")
    changes = apply_updates(warehouse, updates)
    if changes:
        warehouse.data_origin = DataOrigin.MANUAL_ENTRY
        record_audit(db, action="warehouse.update", entity_type="warehouse", entity_id=warehouse.id,
                     organization_id=ctx.org_id, actor_user_id=ctx.user.id, details=changes, request=request)
    commit_or_conflict(db, "A warehouse with this name already exists")
    db.refresh(warehouse)
    return warehouse_out(warehouse, used)


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse(warehouse_id: uuid.UUID, request: Request,
                     ctx: AuthContext = Depends(require(P.WAREHOUSE_MANAGE)), db: Session = Depends(get_db)):
    warehouse = get_accessible_warehouse(db, ctx, warehouse_id)
    if db.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.warehouse_id == warehouse.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Warehouse still holds inventory; remove it first")
    record_audit(db, action="warehouse.delete", entity_type="warehouse", entity_id=warehouse.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id, details={"name": warehouse.name},
                 request=request)
    db.delete(warehouse)
    db.commit()
