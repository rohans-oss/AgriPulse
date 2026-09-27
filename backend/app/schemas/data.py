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
    warnings: int
    error_message: str | None
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
    fetched_at: datetime | None
    freshness: Freshness


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
    wind_kmh: float | None
    weather_code: int | None
    condition: str | None
    fetched_at: datetime


class WeatherNow(BaseModel):
    warehouse: Ref
    region: Ref
    latitude: float | None
    longitude: float | None
    reading: WeatherReading | None
    freshness: Freshness
    source: SourceRef


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
