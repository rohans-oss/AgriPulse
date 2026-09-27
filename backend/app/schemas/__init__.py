import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.models.enums import (
    CommodityCategory,
    MovementType,
    QuantityUnit,
    RecordStatus,
    RoleCode,
    StorageType,
    WarehouseStatus,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
LongName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Ref(ORM):
    id: uuid.UUID
    name: str


# --------------------------------------------------------------------------- auth / users


class RegisterRequest(BaseModel):
    organization_name: LongName
    full_name: Name
    email: EmailStr
    password: Password

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class OrganizationOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    is_demo: bool
    created_at: datetime


class OrganizationUpdate(BaseModel):
    name: LongName


class ScopeOut(BaseModel):
    org_wide: bool
    regions: list[Ref]
    warehouses: list[Ref]
    accessible_warehouse_count: int


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    org_wide_access: bool
    roles: list[str]
    region_ids: list[uuid.UUID]
    warehouse_ids: list[uuid.UUID]
    created_at: datetime
    last_login_at: datetime | None


class MeResponse(BaseModel):
    user: UserOut
    organization: OrganizationOut
    roles: list[str]
    primary_role: str | None
    permissions: list[str]
    scope: ScopeOut


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    me: MeResponse


class UserCreate(BaseModel):
    email: EmailStr
    full_name: Name
    password: Password
    role: RoleCode
    org_wide_access: bool = False
    region_ids: list[uuid.UUID] = []
    warehouse_ids: list[uuid.UUID] = []

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class UserUpdate(BaseModel):
    full_name: Name | None = None
    password: Password | None = None
    role: RoleCode | None = None
    is_active: bool | None = None
    org_wide_access: bool | None = None
    region_ids: list[uuid.UUID] | None = None
    warehouse_ids: list[uuid.UUID] | None = None


class RoleOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str
    permissions: list[str]


# --------------------------------------------------------------------------- regions


class RegionCreate(BaseModel):
    name: Name
    state: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] = ""
    code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=16)] | None = None
    status: RecordStatus = RecordStatus.ACTIVE


class RegionUpdate(BaseModel):
    name: Name | None = None
    state: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=16)] | None = None
    status: RecordStatus | None = None


class RegionOut(ORM):
    id: uuid.UUID
    name: str
    state: str
    code: str | None
    status: RecordStatus
    warehouse_count: int = 0
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- commodities


class CommodityCreate(BaseModel):
    name: Name
    category: CommodityCategory
    unit: QuantityUnit = QuantityUnit.TONNE
    status: RecordStatus = RecordStatus.ACTIVE
    market_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None


class CommodityUpdate(BaseModel):
    name: Name | None = None
    category: CommodityCategory | None = None
    unit: QuantityUnit | None = None
    status: RecordStatus | None = None
    market_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None


class CommodityOut(ORM):
    id: uuid.UUID
    name: str
    category: CommodityCategory
    unit: QuantityUnit
    status: RecordStatus
    market_name: str | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- warehouses


class WarehouseCreate(BaseModel):
    name: LongName
    region_id: uuid.UUID
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] = ""
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    capacity_tonnes: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
    storage_type: StorageType
    status: WarehouseStatus = WarehouseStatus.ACTIVE


class WarehouseUpdate(BaseModel):
    name: LongName | None = None
    region_id: uuid.UUID | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    capacity_tonnes: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)] | None = None
    storage_type: StorageType | None = None
    status: WarehouseStatus | None = None


class WarehouseOut(ORM):
    id: uuid.UUID
    name: str
    region: Ref
    address: str
    latitude: float | None
    longitude: float | None
    capacity_tonnes: float
    used_tonnes: float = 0.0
    utilization_pct: float = 0.0
    storage_type: StorageType
    status: WarehouseStatus
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- inventory


class InventoryCreate(BaseModel):
    warehouse_id: uuid.UUID
    commodity_id: uuid.UUID
    quantity: Quantity
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class InventoryUpdate(BaseModel):
    quantity: Quantity | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] = ""


class CommodityRef(Ref):
    unit: QuantityUnit
    category: CommodityCategory


class WarehouseRef(Ref):
    region_id: uuid.UUID


class InventoryOut(ORM):
    id: uuid.UUID
    warehouse: WarehouseRef
    commodity: CommodityRef
    quantity: float
    unit: QuantityUnit
    quantity_tonnes: float
    notes: str
    created_at: datetime
    updated_at: datetime


class MovementOut(ORM):
    id: uuid.UUID
    warehouse: Ref
    commodity: Ref
    movement_type: MovementType
    quantity_delta: float
    quantity_after: float
    reason: str
    created_at: datetime


class AuditLogOut(ORM):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str | None
    actor_email: str | None
    details: dict
    created_at: datetime
