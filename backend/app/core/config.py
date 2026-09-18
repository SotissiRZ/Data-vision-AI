from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "DataVision AI"
    api_host: str = "0.0.0.0"
    api_port: int = 8005
    cors_origins: str = "http://localhost:3005"
    data_root: Path = Path("./data")
    max_upload_mb: int = 250
    database_url: str = "postgresql+psycopg://datavision:datavision@postgres:5432/datavision"
    redis_url: str = "redis://redis:6379/0"
    ai_provider: str = "disabled"
    ai_model: str = ""
    ai_api_key: str = ""
    auth_secret: str = "change-me-in-production-please-32chars-min"
    access_token_minutes: int = 480
    metadata_fallback_sqlite: bool = True
    worker_poll_seconds: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def upload_dir(self) -> Path:
        path = self.data_root / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def model_dir(self) -> Path:
        path = self.data_root / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
