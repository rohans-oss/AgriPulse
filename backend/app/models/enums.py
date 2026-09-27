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


# --------------------------------------------------------------------------- V2


class DataKind(StrEnum):
    MARKET_PRICES = "MARKET_PRICES"
    WEATHER = "WEATHER"
    INVENTORY = "INVENTORY"


class SourceOrigin(StrEnum):
    OFFICIAL_API = "OFFICIAL_API"  # government / official publisher API
    PUBLIC_API = "PUBLIC_API"  # documented third-party public API
    USER_UPLOAD = "USER_UPLOAD"  # CSV uploaded by an organization user


class RunTrigger(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    UPLOAD = "UPLOAD"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"  # finished, some rows or locations failed
    FAILED = "FAILED"


class IssueSeverity(StrEnum):
    ERROR = "ERROR"  # row rejected
    WARNING = "WARNING"  # row kept, flagged


class WeatherKind(StrEnum):
    CURRENT = "CURRENT"  # latest conditions (provider model analysis)
    DAILY = "DAILY"  # a completed local day
    FORECAST = "FORECAST"  # provider forecast for today (incomplete) or a future day — a model prediction


# --------------------------------------------------------------------------- V3 provenance


class DataOrigin(StrEnum):
    """How an organization-owned record came to exist."""

    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"  # created by the demo seed script
    MANUAL_ENTRY = "MANUAL_ENTRY"  # entered by a user in the app
    CSV_IMPORT = "CSV_IMPORT"  # uploaded by a user
    API = "API"  # pushed by an integration (future)


class DataClass(StrEnum):
    """What the UI is displaying. Every dataset the frontend shows carries one of these."""

    REAL_EXTERNAL = "REAL_EXTERNAL"
    REAL_ORGANIZATION = "REAL_ORGANIZATION"
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    MIXED = "MIXED"  # an aggregate over both synthetic and real organization records
    MODEL_PREDICTION = "MODEL_PREDICTION"
    UNAVAILABLE = "UNAVAILABLE"


class ValidationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_WARNING = "ACCEPTED_WITH_WARNING"


def class_for_origin(origin: "DataOrigin | str") -> DataClass:
    return DataClass.SYNTHETIC_DEMO if str(origin) == DataOrigin.SYNTHETIC_DEMO.value else DataClass.REAL_ORGANIZATION
