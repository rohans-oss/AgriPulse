from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, require
from app.core.database import get_db
from app.models import AuditLog
from app.schemas import AuditLogOut, OrganizationOut, OrganizationUpdate
from app.services.audit import record_audit
from app.services.rbac import P

router = APIRouter(tags=["organization"])


@router.get("/organizations/current", response_model=OrganizationOut)
def current_organization(ctx: AuthContext = Depends(get_auth)):
    return ctx.organization


@router.patch("/organizations/current", response_model=OrganizationOut)
def update_organization(body: OrganizationUpdate, request: Request,
                        ctx: AuthContext = Depends(require(P.SETTINGS_MANAGE)), db: Session = Depends(get_db)):
    org = db.merge(ctx.organization)
    if body.name != org.name:
        record_audit(db, action="organization.update", entity_type="organization", entity_id=org.id,
                     organization_id=org.id, actor_user_id=ctx.user.id, details={"name": [org.name, body.name]},
                     request=request)
        org.name = body.name
        db.commit()
        db.refresh(org)
    return org


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    ctx: AuthContext = Depends(require(P.AUDIT_READ)),
    db: Session = Depends(get_db),
):
    stmt = (select(AuditLog).where(AuditLog.organization_id == ctx.org_id)
            .order_by(AuditLog.created_at.desc()).limit(limit))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return [
        AuditLogOut(id=a.id, action=a.action, entity_type=a.entity_type, entity_id=a.entity_id,
                    actor_email=a.actor.email if a.actor else None, details=a.details, created_at=a.created_at)
        for a in db.scalars(stmt).unique()
    ]
