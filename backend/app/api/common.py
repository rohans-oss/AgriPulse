"""Helpers shared by route modules."""

import uuid
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

T = TypeVar("T")


def get_owned(db: Session, model: type[T], obj_id: uuid.UUID, org_id: uuid.UUID, label: str) -> T:
    """Fetch a row belonging to the caller's organization.

    Rows from other organizations are reported as 404, never 403, so their
    existence is not disclosed.
    """
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "organization_id", None) != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return obj


def flush_or_conflict(db: Session, message: str) -> None:
    """Flush pending changes, translating unique/foreign-key violations into 409."""
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, message) from None


def commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, message) from None


def apply_updates(obj, updates: dict) -> dict:
    """Set changed attributes; return {field: [old, new]} for the audit log."""
    changes = {}
    for key, value in updates.items():
        old = getattr(obj, key)
        if old != value:
            changes[key] = [_jsonable(old), _jsonable(value)]
            setattr(obj, key, value)
    return changes


def _jsonable(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)
