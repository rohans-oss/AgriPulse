import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import flush_or_conflict, get_owned
from app.api.deps import AuthContext, require
from app.api.routes.warehouses import get_accessible_warehouse
from app.core.database import get_db
from app.models import Commodity, InventoryItem, InventoryMovement, Warehouse
from app.models.enums import MovementType, RecordStatus, WarehouseStatus
from app.schemas import InventoryCreate, InventoryOut, InventoryUpdate, MovementOut
from app.services.audit import record_audit
from app.services.rbac import P
from app.services.serializers import inventory_out, movement_out, to_tonnes, warehouse_usage

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _get_item(db: Session, ctx: AuthContext, item_id: uuid.UUID) -> InventoryItem:
    item = get_owned(db, InventoryItem, item_id, ctx.org_id, "Inventory record")
    if not ctx.can_access_warehouse(item.warehouse_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this warehouse")
    return item


def _check_capacity(db: Session, ctx: AuthContext, warehouse: Warehouse, added_tonnes: float) -> None:
    used = warehouse_usage(db, ctx.org_id, [warehouse.id]).get(warehouse.id, 0.0)
    capacity = float(warehouse.capacity_tonnes)
    if used + added_tonnes > capacity + 1e-9:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Exceeds warehouse capacity: {used:.3f} t used + {added_tonnes:.3f} t > {capacity:.3f} t",
        )


def _movement(item: InventoryItem, kind: MovementType, delta: Decimal, reason: str, ctx: AuthContext):
    return InventoryMovement(
        organization_id=ctx.org_id,
        inventory_item_id=item.id,
        warehouse_id=item.warehouse_id,
        commodity_id=item.commodity_id,
        movement_type=kind,
        quantity_delta=delta,
        quantity_after=item.quantity if kind != MovementType.REMOVAL else Decimal(0),
        reason=reason,
        created_by_id=ctx.user.id,
    )


@router.get("", response_model=list[InventoryOut])
def list_inventory(
    warehouse_id: uuid.UUID | None = None,
    commodity_id: uuid.UUID | None = None,
    region_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(require(P.INVENTORY_READ)),
    db: Session = Depends(get_db),
):
    if warehouse_id is not None:
        get_accessible_warehouse(db, ctx, warehouse_id)
    stmt = (
        select(InventoryItem)
        .join(Warehouse, Warehouse.id == InventoryItem.warehouse_id)
        .join(Commodity, Commodity.id == InventoryItem.commodity_id)
        .where(InventoryItem.organization_id == ctx.org_id, ctx.warehouse_filter(InventoryItem.warehouse_id))
        .order_by(Warehouse.name, Commodity.name)
    )
    if warehouse_id:
        stmt = stmt.where(InventoryItem.warehouse_id == warehouse_id)
    if commodity_id:
        stmt = stmt.where(InventoryItem.commodity_id == commodity_id)
    if region_id:
        stmt = stmt.where(Warehouse.region_id == region_id)
    return [inventory_out(i) for i in db.scalars(stmt).unique()]


@router.get("/movements", response_model=list[MovementOut])
def list_movements(
    warehouse_id: uuid.UUID | None = None,
    commodity_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=500),
    ctx: AuthContext = Depends(require(P.INVENTORY_READ)),
    db: Session = Depends(get_db),
):
    if warehouse_id is not None:
        get_accessible_warehouse(db, ctx, warehouse_id)
    stmt = (
        select(InventoryMovement)
        .where(InventoryMovement.organization_id == ctx.org_id, ctx.warehouse_filter(InventoryMovement.warehouse_id))
        .order_by(InventoryMovement.created_at.desc())
        .limit(limit)
    )
    if warehouse_id:
        stmt = stmt.where(InventoryMovement.warehouse_id == warehouse_id)
    if commodity_id:
        stmt = stmt.where(InventoryMovement.commodity_id == commodity_id)
    return [movement_out(m) for m in db.scalars(stmt).unique()]


@router.get("/{item_id}", response_model=InventoryOut)
def get_inventory(item_id: uuid.UUID, ctx: AuthContext = Depends(require(P.INVENTORY_READ)),
                  db: Session = Depends(get_db)):
    return inventory_out(_get_item(db, ctx, item_id))


@router.post("", response_model=InventoryOut, status_code=status.HTTP_201_CREATED)
def create_inventory(body: InventoryCreate, request: Request,
                     ctx: AuthContext = Depends(require(P.INVENTORY_CREATE)), db: Session = Depends(get_db)):
    warehouse = get_accessible_warehouse(db, ctx, body.warehouse_id)
    if warehouse.status != WarehouseStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Warehouse is {warehouse.status.value}; stock cannot be added")
    commodity = db.get(Commodity, body.commodity_id)
    if commodity is None or commodity.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Commodity not found in this organization")
    if commodity.status != RecordStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Commodity is inactive")
    exists = db.scalar(select(InventoryItem.id).where(
        InventoryItem.warehouse_id == warehouse.id, InventoryItem.commodity_id == commodity.id))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{commodity.name} already has a record in {warehouse.name}; update its quantity instead")
    _check_capacity(db, ctx, warehouse, to_tonnes(body.quantity, commodity.unit))

    item = InventoryItem(organization_id=ctx.org_id, warehouse_id=warehouse.id, commodity_id=commodity.id,
                         quantity=body.quantity, notes=body.notes, updated_by_id=ctx.user.id)
    db.add(item)
    flush_or_conflict(db, "Inventory record already exists")
    db.add(_movement(item, MovementType.INITIAL, body.quantity, "Record created", ctx))
    record_audit(db, action="inventory.create", entity_type="inventory_item", entity_id=item.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id,
                 details={"warehouse": warehouse.name, "commodity": commodity.name, "quantity": str(body.quantity)},
                 request=request)
    db.commit()
    db.refresh(item)
    return inventory_out(item)


@router.patch("/{item_id}", response_model=InventoryOut)
def update_inventory(item_id: uuid.UUID, body: InventoryUpdate, request: Request,
                     ctx: AuthContext = Depends(require(P.INVENTORY_UPDATE)), db: Session = Depends(get_db)):
    item = _get_item(db, ctx, item_id)
    details: dict = {}
    if body.quantity is not None and body.quantity != item.quantity:
        delta = body.quantity - item.quantity
        if delta > 0:
            _check_capacity(db, ctx, item.warehouse, to_tonnes(delta, item.commodity.unit))
        details["quantity"] = [str(item.quantity), str(body.quantity)]
        item.quantity = body.quantity
        kind = MovementType.INBOUND if delta > 0 else MovementType.OUTBOUND
        db.add(_movement(item, kind, delta, body.reason, ctx))
    if body.notes is not None and body.notes != item.notes:
        details["notes"] = [item.notes, body.notes]
        item.notes = body.notes
    if details:
        item.updated_by_id = ctx.user.id
        if body.reason:
            details["reason"] = body.reason
        record_audit(db, action="inventory.update", entity_type="inventory_item", entity_id=item.id,
                     organization_id=ctx.org_id, actor_user_id=ctx.user.id,
                     details={"warehouse": item.warehouse.name, "commodity": item.commodity.name, **details},
                     request=request)
    db.commit()
    db.refresh(item)
    return inventory_out(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory(item_id: uuid.UUID, request: Request,
                     ctx: AuthContext = Depends(require(P.INVENTORY_DELETE)), db: Session = Depends(get_db)):
    item = _get_item(db, ctx, item_id)
    db.add(_movement(item, MovementType.REMOVAL, -item.quantity, "Record removed", ctx))
    record_audit(db, action="inventory.delete", entity_type="inventory_item", entity_id=item.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id,
                 details={"warehouse": item.warehouse.name, "commodity": item.commodity.name,
                          "quantity": str(item.quantity)},
                 request=request)
    db.delete(item)
    db.commit()
