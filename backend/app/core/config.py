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
    connector_secret_key: str = ""
    access_token_minutes: int = 60
    refresh_token_days: int = 14
    oidc_state_minutes: int = 10
    frontend_url: str = "http://localhost:3005"
    metadata_fallback_sqlite: bool = True
    deployment_profile: str = "onprem"  # onprem | hybrid
    external_egress_policy: str = "explicit_opt_in"
    worker_poll_seconds: int = 5
    notebook_sandbox_url: str = "http://sandbox:8090"
    notebook_timeout_seconds: int = 20
    notebook_memory_mb: int = 768
    notebook_max_code_chars: int = 100000

    # v2.31 security hardening
    webauthn_enabled: bool = True
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "DataVision AI"
    webauthn_origin: str = "http://localhost:3005"
    mfa_policy: str = "optional"  # optional | required_admin | required_all
    mfa_challenge_minutes: int = 5

    antivirus_mode: str = "disabled"  # disabled | preferred | required
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 8

    secret_kms_key: str = ""
    secret_kms_key_id: str = "primary"
    secret_kms_previous_keys: str = "{}"
    secret_kms_provider: str = "local"  # local | vault_transit
    vault_addr: str = ""
    vault_token: str = ""
    vault_namespace: str = ""
    vault_transit_mount: str = "transit"
    vault_transit_key: str = "datavision"
    vault_transit_hsm_backed: bool = False
    vault_timeout_seconds: int = 5

    # v2.58 session/device hardening
    session_idle_minutes: int = 480
    session_max_hours: int = 336
    session_max_active_per_user: int = 10
    trusted_device_days: int = 30
    managed_device_default_required: bool = False

    # v2.58 OpenTelemetry collector scrape protection
    otel_internal_metrics_token: str = "change-this-otel-metrics-token"

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
