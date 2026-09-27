"""Enumerations shared by models, schemas and business logic."""

import enum


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class RoleCode(StrEnum):
    ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN"
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
    PROCUREMENT_MANAGER = "PROCUREMENT_MANAGER"
    WAREHOUSE_MANAGER = "WAREHOUSE_MANAGER"
    LOGISTICS_MANAGER = "LOGISTICS_MANAGER"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class RecordStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class WarehouseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"


class StorageType(StrEnum):
    NORMAL = "NORMAL"
    COLD_STORAGE = "COLD_STORAGE"
    CONTROLLED = "CONTROLLED"


class CommodityCategory(StrEnum):
    VEGETABLE = "VEGETABLE"
    FRUIT = "FRUIT"
    GRAIN = "GRAIN"
    PULSE = "PULSE"
    SPICE = "SPICE"
    OILSEED = "OILSEED"
    OTHER = "OTHER"


class QuantityUnit(StrEnum):
    TONNE = "TONNE"
    QUINTAL = "QUINTAL"
    KG = "KG"

    @property
    def tonnes_factor(self) -> float:
        return {"TONNE": 1.0, "QUINTAL": 0.1, "KG": 0.001}[self.value]


class MovementType(StrEnum):
    INITIAL = "INITIAL"  # record created with an opening quantity
    INBOUND = "INBOUND"  # quantity increased
    OUTBOUND = "OUTBOUND"  # quantity decreased
    REMOVAL = "REMOVAL"  # record deleted
