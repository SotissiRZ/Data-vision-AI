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

    # v2.59 resilience / disaster recovery
    schema_auto_migrate: bool = True
    backup_retention_count: int = 7
    backup_require_database_dump: bool = True

    # v2.60 SRE / object storage / controlled chaos
    backup_object_store_provider: str = "disabled"  # disabled | s3_compatible
    backup_object_store_endpoint: str = ""
    backup_object_store_bucket: str = ""
    backup_object_store_prefix: str = "datavision/backups"
    backup_object_store_region: str = "us-east-1"
    backup_object_store_access_key: str = ""
    backup_object_store_secret_key: str = ""
    backup_object_store_session_token: str = ""
    backup_object_store_verify_tls: bool = True
    backup_object_store_auto_upload: bool = False
    sre_queue_alert_depth: int = 25
    sre_backup_max_age_hours: int = 26
    sre_restore_drill_max_age_hours: int = 168
    sre_error_budget_burn_alert: float = 2.0
    sre_auto_alerts_enabled: bool = False
    sre_check_interval_seconds: int = 300
    sre_worker_autoscaling_mode: str = "cpu"  # cpu | keda_redis
    sre_chaos_enabled: bool = False
    sre_chaos_max_probe_jobs: int = 20

    # v2.61 automated SRE / multi-zone continuity
    backup_replication_targets_json: str = "[]"
    backup_replication_auto_enabled: bool = False
    sre_default_alert_route_min_severity: str = "medium"
    sre_dr_enabled: bool = False
    sre_dr_allowed_envs: str = "development,test,staging"
    sre_dr_include_dependency_loss_checks: bool = True

    # v2.62 distributed observability / multi-cluster operations
    multi_cluster_sites_json: str = "[]"
    multi_cluster_failover_enabled: bool = False
    multi_cluster_failover_executor: str = "control_plane_only"  # control_plane_only | webhook
    multi_cluster_failover_webhook_url: str = ""
    multi_cluster_failover_webhook_secret: str = ""
    multi_cluster_failover_webhook_timeout_seconds: int = 10
    multi_cluster_confirmation_ttl_minutes: int = 10
    multi_cluster_require_verified_backup: bool = True
    multi_cluster_backup_max_age_hours: int = 26

    # v2.63 operational security / supply chain
    secret_auto_rotation_enabled: bool = False
    secret_rotation_default_days: int = 90
    secret_rotation_generated_bytes: int = 32
    release_rollback_enabled: bool = False
    release_rollback_executor: str = "plan_only"  # plan_only | webhook
    release_rollback_webhook_url: str = ""
    release_rollback_webhook_secret: str = ""
    release_rollback_timeout_seconds: int = 10
    release_rollback_confirmation_ttl_minutes: int = 10

    # v2.64 admission / runtime security / continuous compliance
    admission_verify_images_enabled: bool = False
    runtime_security_seccomp_runtime_default: bool = True
    runtime_security_run_as_non_root: bool = True
    runtime_security_read_only_root_filesystem: bool = True
    runtime_security_drop_all_capabilities: bool = True
    runtime_security_disallow_privilege_escalation: bool = True
    runtime_detection_enabled: bool = False
    continuous_compliance_enabled: bool = False
    continuous_compliance_schedule: str = "23 */6 * * *"

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
