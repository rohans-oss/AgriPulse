from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables / backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AgriFlow AI"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://agriflow:agriflow@localhost:5432/agriflow"

    jwt_secret: str = "change-me-in-development-only-please-32b"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    bcrypt_rounds: int = 12

    session_cookie_name: str = "agriflow_session"
    cookie_secure: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]

    # --- V2 external data -------------------------------------------------
    # Free key from https://data.gov.in (My Account → API key). Without it the
    # mandi price source reports "Not configured" and is never faked.
    data_gov_in_api_key: str = ""
    ogd_api_base: str = "https://api.data.gov.in/resource"
    ogd_mandi_resource_id: str = "9ef84268-d588-465a-a308-a864a43d0070"
    mandi_states: list[str] = ["Karnataka"]
    open_meteo_base: str = "https://api.open-meteo.com/v1/forecast"
    http_timeout_seconds: float = 20.0
    http_retries: int = 1
    http_backoff_seconds: float = 2.0

    # --- V3 scheduler -------------------------------------------------------
    # Weather: Open-Meteo refreshes current conditions every 15 min; hourly polling is plenty.
    weather_refresh_minutes: int = 60
    # Mandi prices: the dataset is updated through the day as mandis report; fetch a few times daily (IST).
    market_fetch_times_ist: list[str] = ["10:30", "14:30", "19:30"]
    retry_after_failure_minutes: int = 20
    max_upload_bytes: int = 5_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
