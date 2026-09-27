import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import apply_updates, commit_or_conflict, flush_or_conflict, get_owned
from app.api.deps import AuthContext, require
from app.core.database import get_db
from app.models import Region, Warehouse
from app.schemas import RegionCreate, RegionOut, RegionUpdate
from app.services.audit import record_audit
from app.services.rbac import P

router = APIRouter(prefix="/regions", tags=["regions"])


def _counts(db: Session, ctx: AuthContext) -> dict[uuid.UUID, int]:
    stmt = (
        select(Warehouse.region_id, func.count())
        .where(Warehouse.organization_id == ctx.org_id, ctx.warehouse_filter(Warehouse.id))
        .group_by(Warehouse.region_id)
    )
    return dict(db.execute(stmt).all())


def _out(region: Region, count: int) -> RegionOut:
    out = RegionOut.model_validate(region)
    out.warehouse_count = count
    return out


@router.get("", response_model=list[RegionOut])
def list_regions(ctx: AuthContext = Depends(require(P.REGION_READ)), db: Session = Depends(get_db)):
    """Regions are organization reference data; warehouse counts respect location scope."""
    counts = _counts(db, ctx)
    regions = db.scalars(select(Region).where(Region.organization_id == ctx.org_id).order_by(Region.name))
    return [_out(r, counts.get(r.id, 0)) for r in regions]


@router.get("/{region_id}", response_model=RegionOut)
def get_region(region_id: uuid.UUID, ctx: AuthContext = Depends(require(P.REGION_READ)), db: Session = Depends(get_db)):
    region = get_owned(db, Region, region_id, ctx.org_id, "Region")
    return _out(region, _counts(db, ctx).get(region.id, 0))


@router.post("", response_model=RegionOut, status_code=status.HTTP_201_CREATED)
def create_region(body: RegionCreate, request: Request,
                  ctx: AuthContext = Depends(require(P.REGION_MANAGE)), db: Session = Depends(get_db)):
    region = Region(organization_id=ctx.org_id, **body.model_dump())
    db.add(region)
    flush_or_conflict(db, "A region with this name already exists")
    record_audit(db, action="region.create", entity_type="region", entity_id=region.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id, details={"name": region.name}, request=request)
    db.commit()
    return _out(region, 0)


@router.patch("/{region_id}", response_model=RegionOut)
def update_region(region_id: uuid.UUID, body: RegionUpdate, request: Request,
                  ctx: AuthContext = Depends(require(P.REGION_MANAGE)), db: Session = Depends(get_db)):
    region = get_owned(db, Region, region_id, ctx.org_id, "Region")
    changes = apply_updates(region, body.model_dump(exclude_unset=True))
    if changes:
        record_audit(db, action="region.update", entity_type="region", entity_id=region.id,
                     organization_id=ctx.org_id, actor_user_id=ctx.user.id, details=changes, request=request)
    commit_or_conflict(db, "A region with this name already exists")
    return _out(region, _counts(db, ctx).get(region.id, 0))


@router.delete("/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_region(region_id: uuid.UUID, request: Request,
                  ctx: AuthContext = Depends(require(P.REGION_MANAGE)), db: Session = Depends(get_db)):
    region = get_owned(db, Region, region_id, ctx.org_id, "Region")
    if db.scalar(select(func.count()).select_from(Warehouse).where(Warehouse.region_id == region.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Region still has warehouses; move or remove them first")
    record_audit(db, action="region.delete", entity_type="region", entity_id=region.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id, details={"name": region.name}, request=request)
    db.delete(region)
    db.commit()
