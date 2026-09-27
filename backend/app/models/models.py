"""SQLAlchemy ORM models for AgriFlow AI V1.

Tenancy rule: every organization-owned row carries ``organization_id`` and
every query in the API layer filters on it (see app/services/access.py).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    CommodityCategory,
    MovementType,
    QuantityUnit,
    RecordStatus,
    StorageType,
    WarehouseStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def enum_col(enum_cls, length: int = 32):
    # Stored as VARCHAR + CHECK constraint: portable and easy to extend via migrations.
    return Enum(enum_cls, native_enum=False, length=length, validate_strings=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# --------------------------------------------------------------------------- tenancy


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    # True for seeded demo workspaces; the UI labels all of their values as synthetic.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Fail-closed location scope: a non-admin user sees only the regions/warehouses
    # listed in user_location_scopes unless this flag is set.
    org_wide_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship()
    role_assignments: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    location_scopes: Mapped[list["UserLocationScope"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class AuthSession(Base):
    """Server-side session record backing each JWT, so logout really revokes it."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- RBAC


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class Role(TimestampMixin, Base):
    """System roles have organization_id NULL; custom per-org roles (later) set it."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_roles_org_code"),
        # NULLs are distinct in unique constraints, so system roles need their own index.
        Index(
            "uq_roles_system_code",
            "code",
            unique=True,
            postgresql_where=text("organization_id IS NULL"),
            sqlite_where=text("organization_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    permissions: Mapped[list[Permission]] = relationship(secondary="role_permissions", lazy="selectin")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="role_assignments")
    role: Mapped[Role] = relationship(lazy="selectin")


class UserLocationScope(Base):
    """One row grants access to a whole region or to a single warehouse."""

    __tablename__ = "user_location_scopes"
    __table_args__ = (
        CheckConstraint(
            "(region_id IS NOT NULL AND warehouse_id IS NULL) OR (region_id IS NULL AND warehouse_id IS NOT NULL)",
            name="exactly_one_target",
        ),
        UniqueConstraint("user_id", "region_id", "warehouse_id", name="uq_user_location_scopes_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), index=True
    )

    user: Mapped[User] = relationship(back_populates="location_scopes")


# --------------------------------------------------------------------------- master data


class Region(TimestampMixin, Base):
    __tablename__ = "regions"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_regions_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    code: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[RecordStatus] = mapped_column(enum_col(RecordStatus), default=RecordStatus.ACTIVE, nullable=False)


class Commodity(TimestampMixin, Base):
    __tablename__ = "commodities"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_commodities_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[CommodityCategory] = mapped_column(enum_col(CommodityCategory), nullable=False)
    unit: Mapped[QuantityUnit] = mapped_column(enum_col(QuantityUnit), default=QuantityUnit.TONNE, nullable=False)
    status: Mapped[RecordStatus] = mapped_column(enum_col(RecordStatus), default=RecordStatus.ACTIVE, nullable=False)


class Warehouse(TimestampMixin, Base):
    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_warehouses_org_name"),
        CheckConstraint("capacity_tonnes > 0", name="capacity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    capacity_tonnes: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    storage_type: Mapped[StorageType] = mapped_column(enum_col(StorageType), nullable=False)
    status: Mapped[WarehouseStatus] = mapped_column(
        enum_col(WarehouseStatus), default=WarehouseStatus.ACTIVE, nullable=False
    )

    region: Mapped[Region] = relationship(lazy="joined")


class InventoryItem(TimestampMixin, Base):
    """Current stock of one commodity in one warehouse."""

    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "commodity_id", name="uq_inventory_items_warehouse_commodity"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        Index("ix_inventory_items_org_commodity", "organization_id", "commodity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    warehouse: Mapped[Warehouse] = relationship(lazy="joined")
    commodity: Mapped[Commodity] = relationship(lazy="joined")


class InventoryMovement(Base):
    """Append-only ledger of quantity changes; source of inbound/outbound history."""

    __tablename__ = "inventory_movements"
    __table_args__ = (Index("ix_inventory_movements_org_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Kept as plain references (no cascade) so history survives record removal.
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="SET NULL"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[MovementType] = mapped_column(enum_col(MovementType), nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    warehouse: Mapped[Warehouse] = relationship(lazy="joined")
    commodity: Mapped[Commodity] = relationship(lazy="joined")


# --------------------------------------------------------------------------- audit


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    actor: Mapped[User | None] = relationship(lazy="joined")


__all__ = [
    "AuditLog",
    "AuthSession",
    "Commodity",
    "InventoryItem",
    "InventoryMovement",
    "Organization",
    "Permission",
    "Region",
    "Role",
    "RolePermission",
    "User",
    "UserLocationScope",
    "UserRole",
    "Warehouse",
]
