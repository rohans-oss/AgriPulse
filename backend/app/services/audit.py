from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    organization_id=None,
    actor_user_id=None,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    """Add an audit row to the current transaction (committed with the change it describes)."""
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details or {},
            ip_address=request.client.host if request and request.client else None,
        )
    )
