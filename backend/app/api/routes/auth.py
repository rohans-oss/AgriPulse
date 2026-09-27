import re
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, build_context, get_auth
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, session_expiry, verify_password
from app.models import AuthSession, Organization, User, UserRole
from app.models.enums import RoleCode
from app.schemas import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.services.audit import record_audit
from app.services.rbac import get_system_role
from app.services.serializers import me_out

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash compared against when the email is unknown, so timing doesn't reveal accounts.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    return f"{base}-{secrets.token_hex(3)}"


def _start_session(db: Session, user: User, response: Response) -> TokenResponse:
    expires_at = session_expiry()
    session = AuthSession(user_id=user.id, expires_at=expires_at)
    db.add(session)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, session.id, expires_at)
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    ctx = build_context(db, user, session.id)
    return TokenResponse(access_token=token, expires_at=expires_at, me=me_out(db, ctx))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Create a new organization with the caller as its Organization Admin."""
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    admin_role = get_system_role(db, RoleCode.ORGANIZATION_ADMIN)
    if admin_role is None:  # pragma: no cover - catalog is synced on startup
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Role catalog not initialised")

    org = Organization(name=body.organization_name, slug=slugify(body.organization_name))
    db.add(org)
    db.flush()
    user = User(
        organization_id=org.id,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        org_wide_access=True,
    )
    user.role_assignments = [UserRole(role=admin_role)]
    db.add(user)
    db.flush()
    record_audit(db, action="organization.create", entity_type="organization", entity_id=org.id,
                 organization_id=org.id, actor_user_id=user.id, details={"name": org.name}, request=request)
    record_audit(db, action="user.register", entity_type="user", entity_id=user.id,
                 organization_id=org.id, actor_user_id=user.id, details={"email": user.email}, request=request)
    return _start_session(db, user, response)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not valid:
        if user is not None:
            record_audit(db, action="auth.login_failed", entity_type="user", entity_id=user.id,
                         organization_id=user.organization_id, request=request)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    record_audit(db, action="auth.login", entity_type="user", entity_id=user.id,
                 organization_id=user.organization_id, actor_user_id=user.id, request=request)
    return _start_session(db, user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    session = db.get(AuthSession, ctx.session_id)
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
    record_audit(db, action="auth.logout", entity_type="user", entity_id=ctx.user.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id, request=request)
    db.commit()
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    resp.delete_cookie(get_settings().session_cookie_name, path="/")
    return resp


@router.get("/me", response_model=MeResponse)
def me(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return me_out(db, ctx)
