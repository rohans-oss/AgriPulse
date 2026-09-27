import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas import Ref
from app.services.data.freshness import Freshness


class SourceRef(BaseModel):
    key: str
    name: str
    origin: str


class RunOut(BaseModel):
    id: uuid.UUID
    source: SourceRef
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    rows_received: int
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    rows_rejected: int
    rows_duplicate: int = 0
    warnings: int
    error_message: str | None
    error_kind: str | None = None
    endpoint: str | None = None
    scope: str = "ORGANIZATION"  # ORGANIZATION | PUBLIC (shared public-data fetch)
    file_name: str | None
    triggered_by: str | None
    params: dict


class IssueOut(BaseModel):
    row_number: int | None
    field: str | None
    severity: str
    code: str
    message: str
    raw: dict


class RunDetail(RunOut):
    issues: list[IssueOut]


class SourceStatus(BaseModel):
    key: str
    name: str
    publisher: str
    kind: str
    origin: str
    homepage_url: str
    license: str
    update_frequency: str
    description: str
    configured: bool
    config_message: str | None
    can_run: bool
    can_upload: bool
    record_count: int
    latest_observation: str | None
    freshness: Freshness | None
    last_run: RunOut | None
    last_success_at: datetime | None
    # --- V3 source health
    data_class: str = "REAL_EXTERNAL"
    status: str = "NOT_CONNECTED"  # CONNECTED | DEGRADED | FAILING | NOT_CONFIGURED | NOT_CONNECTED | UPLOAD_ONLY | DISABLED
    status_detail: str = ""
    endpoint: str | None = None
    auth_status: str = "NOT_REQUIRED"  # NOT_REQUIRED | CONFIGURED | MISSING | REJECTED
    enabled: bool = True
    auto_refresh: bool | None = None
    can_configure: bool = False
    expected_refresh: str = ""
    last_fetch_started_at: datetime | None = None
    last_fetch_completed_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_failure_message: str | None = None
    last_failure_kind: str | None = None
    last_rows_received: int | None = None
    last_rows_accepted: int | None = None
    last_rows_rejected: int | None = None
    last_rows_duplicate: int | None = None
    next_scheduled_at: datetime | None = None
    scheduler_running: bool = False
    scheduler_heartbeat_at: datetime | None = None


class PriceOut(BaseModel):
    id: uuid.UUID
    state: str
    district: str
    market: str
    commodity: str
    variety: str
    grade: str
    arrival_date: date
    min_price: float | None
    max_price: float | None
    modal_price: float
    unit: str = "INR/quintal"
    source: SourceRef
    fetched_at: datetime
    data_class: str = "REAL_EXTERNAL"
    validation_status: str = "ACCEPTED"
    validation_notes: list[str] | None = None
    run_id: uuid.UUID | None = None


class PriceDetail(PriceOut):
    """Full provenance for one stored observation."""

    source_record_id: str | None
    source_dataset: str | None
    source_endpoint: str | None
    raw_reference: dict | None
    publisher: str
    run: RunOut | None  # None if the run is not visible to this organization


class CompareRow(BaseModel):
    name: str
    latest_date: date
    modal: float
    low: float | None
    high: float | None
    reports: int


class Compare(BaseModel):
    commodity: str
    by: str
    source: SourceRef | None
    window_days: int
    rows: list[CompareRow]
    freshness: Freshness


class PricePage(BaseModel):
    total: int
    rows: list[PriceOut]


class LatestPrice(BaseModel):
    commodity: str
    in_catalog: bool
    source: SourceRef | None
    latest_date: date | None
    markets_reporting: int
    avg_modal: float | None
    min_modal: float | None
    max_modal: float | None
    previous_date: date | None
    previous_avg_modal: float | None
    change_pct: float | None
    change_abs: float | None = None
    fetched_at: datetime | None
    freshness: Freshness
    data_class: str = "UNAVAILABLE"


class TrendPoint(BaseModel):
    date: date
    modal: float
    low: float | None
    high: float | None
    markets: int


class TrendSeries(BaseModel):
    label: str
    points: list[TrendPoint]


class Trend(BaseModel):
    commodity: str
    source: SourceRef | None
    series: list[TrendSeries]
    freshness: Freshness


class FilterCommodity(BaseModel):
    name: str
    rows: int
    latest_date: date | None
    in_catalog: bool


class MarketFilters(BaseModel):
    states: list[str]
    districts: list[str]
    markets: list[str]
    commodities: list[FilterCommodity]
    sources: list[SourceRef]


class WeatherReading(BaseModel):
    observed_at: datetime
    temperature_c: float | None
    humidity_pct: float | None
    precipitation_mm: float | None
    rain_mm: float | None = None
    wind_kmh: float | None
    wind_gust_kmh: float | None = None
    weather_code: int | None
    condition: str | None
    fetched_at: datetime
    run_id: uuid.UUID | None = None
    validation_status: str = "ACCEPTED"


class ForecastDay(BaseModel):
    """Provider forecast (a model prediction, not an observation)."""

    date: date
    temp_max_c: float | None
    temp_min_c: float | None
    precipitation_mm: float | None
    precipitation_probability: float | None
    wind_max_kmh: float | None
    weather_code: int | None
    condition: str | None
    issued_at: datetime


class Indicator(BaseModel):
    key: str  # RAIN | HEAT | WIND | STORM | HUMIDITY
    level: str  # WATCH | WARNING
    title: str
    message: str
    basis: str  # OBSERVED | FORECAST
    data_class: str  # REAL_EXTERNAL | MODEL_PREDICTION
    rule: str
    as_of: datetime | date


class WeatherNow(BaseModel):
    warehouse: Ref
    region: Ref
    latitude: float | None
    longitude: float | None
    reading: WeatherReading | None
    freshness: Freshness
    source: SourceRef
    data_class: str = "UNAVAILABLE"
    stale: bool = False
    forecast: list[ForecastDay] = []
    indicators: list[Indicator] = []
    indicators_note: str | None = None


class WeatherDay(BaseModel):
    date: date
    temp_max_c: float | None
    temp_min_c: float | None
    precipitation_mm: float | None


class WeatherHistory(BaseModel):
    warehouse: Ref
    days: list[WeatherDay]
    source: SourceRef
    freshness: Freshness


class ImportIssue(IssueOut):
    pass


class ImportResult(BaseModel):
    dry_run: bool
    run_id: uuid.UUID | None
    file_name: str
    columns_detected: dict[str, str]
    missing_columns: list[str]
    rows_total: int
    rows_valid: int
    rows_rejected: int
    warnings: int
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    issues: list[IssueOut]
    preview: list[dict]


class EnvironmentItem(BaseModel):
    key: str
    label: str
    data_class: str  # REAL_EXTERNAL | REAL_ORGANIZATION | SYNTHETIC_DEMO | MIXED | MODEL_PREDICTION | UNAVAILABLE
    status: str  # ok | warn | bad | none
    summary: str
    detail: str
    source: str | None = None
    as_of: datetime | None = None
    counts: dict[str, int] | None = None


class DataEnvironment(BaseModel):
    items: list[EnvironmentItem]
    last_successful_sync: datetime | None
    generated_at: datetime


class SourceSettingsUpdate(BaseModel):
    auto_refresh: bool
