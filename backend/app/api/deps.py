"""Authorization context: User → Organization → Role → Permissions → Location scope.

Every protected endpoint receives an ``AuthContext`` built here. Endpoints never
trust client-supplied organization ids; tenancy and scope come only from the
authenticated session.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import AuthSession, Organization, User, Warehouse
from app.services.rbac import DASHBOARD_PRIORITY, ORG_WIDE_ROLES


@dataclass
class AuthContext:
    user: User
    organization: Organization
    session_id: uuid.UUID
    role_codes: list[str]
    permissions: set[str]
    org_wide: bool
    scoped_region_ids: set[uuid.UUID] = field(default_factory=set)
    scoped_warehouse_ids: set[uuid.UUID] = field(default_factory=set)
    # None means "every warehouse in the organization".
    allowed_warehouse_ids: set[uuid.UUID] | None = None

    @property
    def org_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def primary_role(self) -> str | None:
        for code in DASHBOARD_PRIORITY:
            if code.value in self.role_codes:
                return code.value
        return self.role_codes[0] if self.role_codes else None

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")

    def can_access_warehouse(self, warehouse_id: uuid.UUID) -> bool:
        return self.allowed_warehouse_ids is None or warehouse_id in self.allowed_warehouse_ids

    def can_manage_in_region(self, region_id: uuid.UUID) -> bool:
        return self.org_wide or region_id in self.scoped_region_ids

    def warehouse_filter(self, column):
        """SQL predicate limiting a warehouse_id column to the user's scope."""
        if self.allowed_warehouse_ids is None:
            return True
        return column.in_(self.allowed_warehouse_ids or [uuid.UUID(int=0)])


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(get_settings().session_cookie_name)


def resolve_allowed_warehouses(db: Session, user: User, org_wide: bool) -> tuple[set, set, set | None]:
    region_ids = {s.region_id for s in user.location_scopes if s.region_id}
    warehouse_ids = {s.warehouse_id for s in user.location_scopes if s.warehouse_id}
    if org_wide:
        return region_ids, warehouse_ids, None
    if not region_ids and not warehouse_ids:
        return region_ids, warehouse_ids, set()  # fail closed
    allowed = set(
        db.scalars(
            select(Warehouse.id).where(
                Warehouse.organization_id == user.organization_id,
                or_(Warehouse.id.in_(warehouse_ids or [uuid.UUID(int=0)]), Warehouse.region_id.in_(region_ids or [uuid.UUID(int=0)])),
            )
        )
    )
    return region_ids, warehouse_ids, allowed


def build_context(db: Session, user: User, session_id: uuid.UUID) -> AuthContext:
    role_codes = [ra.role.code for ra in user.role_assignments]
    permissions = {p.code for ra in user.role_assignments for p in ra.role.permissions}
    org_wide = user.org_wide_access or any(code in ORG_WIDE_ROLES for code in role_codes)
    region_ids, warehouse_ids, allowed = resolve_allowed_warehouses(db, user, org_wide)
    return AuthContext(
        user=user,
        organization=user.organization,
        session_id=session_id,
        role_codes=role_codes,
        permissions=permissions,
        org_wide=org_wide,
        scoped_region_ids=region_ids,
        scoped_warehouse_ids=warehouse_ids,
        allowed_warehouse_ids=allowed,
    )


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    token = extract_token(request)
    if not token:
        raise _unauthorized()
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized("Invalid or expired token") from None

    session = db.get(AuthSession, session_id)
    now = datetime.now(UTC)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or session.expires_at.replace(tzinfo=session.expires_at.tzinfo or UTC) <= now
    ):
        raise _unauthorized("Session expired or signed out")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Account is inactive")
    return build_context(db, user, session_id)


def require(*permissions: str):
    """Dependency factory: ``ctx = Depends(require(P.INVENTORY_READ))``."""

    def dependency(ctx: AuthContext = Depends(get_auth)) -> AuthContext:
        for perm in permissions:
            ctx.require(perm)
        return ctx

    return dependency
