import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import apply_updates, commit_or_conflict, flush_or_conflict, get_owned
from app.api.deps import AuthContext, require
from app.core.database import get_db
from app.models import Commodity, InventoryItem
from app.models.enums import CommodityCategory, RecordStatus
from app.schemas import CommodityCreate, CommodityOut, CommodityUpdate
from app.services.audit import record_audit
from app.services.rbac import P

router = APIRouter(prefix="/commodities", tags=["commodities"])


def _has_inventory(db: Session, commodity_id: uuid.UUID) -> bool:
    return bool(db.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.commodity_id == commodity_id)))


@router.get("", response_model=list[CommodityOut])
def list_commodities(
    category: CommodityCategory | None = None,
    status_filter: RecordStatus | None = Query(None, alias="status"),
    ctx: AuthContext = Depends(require(P.COMMODITY_READ)),
    db: Session = Depends(get_db),
):
    stmt = select(Commodity).where(Commodity.organization_id == ctx.org_id).order_by(Commodity.name)
    if category:
        stmt = stmt.where(Commodity.category == category)
    if status_filter:
        stmt = stmt.where(Commodity.status == status_filter)
    return db.scalars(stmt).all()


@router.get("/{commodity_id}", response_model=CommodityOut)
def get_commodity(commodity_id: uuid.UUID, ctx: AuthContext = Depends(require(P.COMMODITY_READ)),
                  db: Session = Depends(get_db)):
    return get_owned(db, Commodity, commodity_id, ctx.org_id, "Commodity")


@router.post("", response_model=CommodityOut, status_code=status.HTTP_201_CREATED)
def create_commodity(body: CommodityCreate, request: Request,
                     ctx: AuthContext = Depends(require(P.COMMODITY_MANAGE)), db: Session = Depends(get_db)):
    commodity = Commodity(organization_id=ctx.org_id, **body.model_dump())
    db.add(commodity)
    flush_or_conflict(db, "A commodity with this name already exists")
    record_audit(db, action="commodity.create", entity_type="commodity", entity_id=commodity.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id,
                 details={"name": commodity.name, "unit": commodity.unit.value}, request=request)
    db.commit()
    return commodity


@router.patch("/{commodity_id}", response_model=CommodityOut)
def update_commodity(commodity_id: uuid.UUID, body: CommodityUpdate, request: Request,
                     ctx: AuthContext = Depends(require(P.COMMODITY_MANAGE)), db: Session = Depends(get_db)):
    commodity = get_owned(db, Commodity, commodity_id, ctx.org_id, "Commodity")
    updates = body.model_dump(exclude_unset=True)
    if "unit" in updates and updates["unit"] != commodity.unit and _has_inventory(db, commodity.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Unit cannot change while inventory exists for this commodity")
    changes = apply_updates(commodity, updates)
    if changes:
        record_audit(db, action="commodity.update", entity_type="commodity", entity_id=commodity.id,
                     organization_id=ctx.org_id, actor_user_id=ctx.user.id, details=changes, request=request)
    commit_or_conflict(db, "A commodity with this name already exists")
    return commodity


@router.delete("/{commodity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_commodity(commodity_id: uuid.UUID, request: Request,
                     ctx: AuthContext = Depends(require(P.COMMODITY_MANAGE)), db: Session = Depends(get_db)):
    commodity = get_owned(db, Commodity, commodity_id, ctx.org_id, "Commodity")
    if _has_inventory(db, commodity.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Commodity has inventory records; remove them or mark the commodity INACTIVE")
    record_audit(db, action="commodity.delete", entity_type="commodity", entity_id=commodity.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id, details={"name": commodity.name},
                 request=request)
    db.delete(commodity)
    db.commit()
