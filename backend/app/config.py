from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://testharbor:testharbor@localhost:5433/testharbor"
    secret_key: str = "change-me-please"
    session_max_age_days: int = 14
    seed_demo: bool = True
    # Set to true when serving over HTTPS so the session cookie gets the Secure flag.
    secure_cookies: bool = False
    # Runs' HTML reports uploaded by agents (a volume in docker-compose.yml).
    reports_dir: str = "/data/reports"
    max_report_mb: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
