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


@lru_cache
def get_settings() -> Settings:
    return Settings()
