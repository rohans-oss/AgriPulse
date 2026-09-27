import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.common import get_owned
from app.api.deps import AuthContext, require
from app.core.database import get_db
from app.core.security import hash_password
from app.models import AuthSession, Region, Role, User, UserLocationScope, UserRole, Warehouse
from app.models.enums import RoleCode
from app.schemas import RoleOut, UserCreate, UserOut, UserUpdate
from app.services.audit import record_audit
from app.services.rbac import ORG_WIDE_ROLES, P, get_system_role
from app.services.serializers import user_out

router = APIRouter(tags=["users"])


def _validate_scope(db: Session, ctx: AuthContext, region_ids: list[uuid.UUID], warehouse_ids: list[uuid.UUID]):
    region_ids, warehouse_ids = set(region_ids), set(warehouse_ids)
    if region_ids:
        found = set(db.scalars(select(Region.id).where(Region.organization_id == ctx.org_id, Region.id.in_(region_ids))))
        if found != region_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "One or more regions are not in this organization")
    if warehouse_ids:
        found = set(db.scalars(select(Warehouse.id).where(Warehouse.organization_id == ctx.org_id,
                                                         Warehouse.id.in_(warehouse_ids))))
        if found != warehouse_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "One or more warehouses are not in this organization")
    return ([UserLocationScope(region_id=r) for r in region_ids]
            + [UserLocationScope(warehouse_id=w) for w in warehouse_ids])


def _role(db: Session, code: RoleCode) -> Role:
    role = get_system_role(db, code)
    if role is None:  # pragma: no cover
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown role")
    return role


def _active_admin_count(db: Session, org_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(User.organization_id == org_id, User.is_active.is_(True),
               Role.code == RoleCode.ORGANIZATION_ADMIN.value)
    ) or 0


def _revoke_sessions(db: Session, user_id: uuid.UUID) -> None:
    db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
               .values(revoked_at=datetime.now(UTC)))


@router.get("/roles", response_model=list[RoleOut])
def list_roles(ctx: AuthContext = Depends(require(P.USERS_READ)), db: Session = Depends(get_db)):
    roles = db.scalars(select(Role).where((Role.organization_id.is_(None)) | (Role.organization_id == ctx.org_id)))
    return [RoleOut(id=r.id, code=r.code, name=r.name, description=r.description,
                    permissions=sorted(p.code for p in r.permissions)) for r in roles]


@router.get("/users", response_model=list[UserOut])
def list_users(ctx: AuthContext = Depends(require(P.USERS_READ)), db: Session = Depends(get_db)):
    users = db.scalars(select(User).where(User.organization_id == ctx.org_id).order_by(User.full_name))
    return [user_out(u) for u in users]


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, ctx: AuthContext = Depends(require(P.USERS_READ)), db: Session = Depends(get_db)):
    return user_out(get_owned(db, User, user_id, ctx.org_id, "User"))


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, request: Request,
                ctx: AuthContext = Depends(require(P.USERS_MANAGE)), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        organization_id=ctx.org_id,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        org_wide_access=body.org_wide_access or body.role.value in ORG_WIDE_ROLES,
    )
    user.role_assignments = [UserRole(role=_role(db, body.role))]
    user.location_scopes = _validate_scope(db, ctx, body.region_ids, body.warehouse_ids)
    db.add(user)
    db.flush()
    record_audit(db, action="user.create", entity_type="user", entity_id=user.id, organization_id=ctx.org_id,
                 actor_user_id=ctx.user.id,
                 details={"email": user.email, "role": body.role.value, "org_wide_access": user.org_wide_access,
                          "region_ids": [str(r) for r in body.region_ids],
                          "warehouse_ids": [str(w) for w in body.warehouse_ids]},
                 request=request)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, request: Request,
                ctx: AuthContext = Depends(require(P.USERS_MANAGE)), db: Session = Depends(get_db)):
    user = get_owned(db, User, user_id, ctx.org_id, "User")
    details: dict = {}
    is_self = user.id == ctx.user.id
    was_admin = any(ra.role.code == RoleCode.ORGANIZATION_ADMIN.value for ra in user.role_assignments)

    losing_admin = was_admin and (
        (body.role is not None and body.role != RoleCode.ORGANIZATION_ADMIN) or body.is_active is False
    )
    if losing_admin and is_self:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove your own admin access or deactivate yourself")
    if losing_admin and user.is_active and _active_admin_count(db, ctx.org_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "The organization must keep at least one active admin")

    if body.full_name is not None and body.full_name != user.full_name:
        details["full_name"] = [user.full_name, body.full_name]
        user.full_name = body.full_name
    if body.role is not None:
        current = [ra.role.code for ra in user.role_assignments]
        if current != [body.role.value]:
            details["roles"] = [current, [body.role.value]]
            user.role_assignments = [UserRole(role=_role(db, body.role))]
            db.flush()
    if body.org_wide_access is not None and body.org_wide_access != user.org_wide_access:
        details["org_wide_access"] = [user.org_wide_access, body.org_wide_access]
        user.org_wide_access = body.org_wide_access
    if body.region_ids is not None or body.warehouse_ids is not None:
        region_ids = body.region_ids if body.region_ids is not None else [s.region_id for s in user.location_scopes if s.region_id]
        warehouse_ids = (body.warehouse_ids if body.warehouse_ids is not None
                         else [s.warehouse_id for s in user.location_scopes if s.warehouse_id])
        scopes = _validate_scope(db, ctx, region_ids, warehouse_ids)
        user.location_scopes = []
        db.flush()
        user.location_scopes = scopes
        details["location_scope"] = {"region_ids": [str(r) for r in set(region_ids)],
                                     "warehouse_ids": [str(w) for w in set(warehouse_ids)]}
    if any(ra.role.code in ORG_WIDE_ROLES for ra in user.role_assignments):
        user.org_wide_access = True
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        details["password"] = "changed"
        _revoke_sessions(db, user.id)
    if body.is_active is not None and body.is_active != user.is_active:
        details["is_active"] = [user.is_active, body.is_active]
        user.is_active = body.is_active
        if not body.is_active:
            _revoke_sessions(db, user.id)

    if details:
        record_audit(db, action="user.update", entity_type="user", entity_id=user.id, organization_id=ctx.org_id,
                     actor_user_id=ctx.user.id, details=details, request=request)
    db.commit()
    db.refresh(user)
    return user_out(user)
