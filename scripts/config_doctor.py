#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

PLACEHOLDER_PREFIXES = ("change-this", "change-", "changeme", "example")
REQUIRED = ("APP_ENV", "DATABASE_URL", "REDIS_URL", "AUTH_SECRET", "CONNECTOR_SECRET_KEY")


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        raise FileNotFoundError(path)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(normalized.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)


def inspect(root: Path, env_file: Path, mode: str | None = None) -> dict:
    values = parse_env(env_file)
    errors: list[str] = []
    warnings: list[str] = []
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    effective_mode = (mode or values.get("APP_ENV") or "development").strip().lower()

    for key in REQUIRED:
        if not values.get(key):
            errors.append(f"missing:{key}")

    for key in ("DATABASE_URL", "REDIS_URL"):
        value = values.get(key, "")
        if value and not urlparse(value).scheme:
            errors.append(f"invalid_url:{key}")

    auth_mode = values.get("AUTH_MODE", "required").strip().lower() or "required"
    if auth_mode not in {"required", "local_dev"}:
        errors.append("unsupported_auth_mode")
    if effective_mode == "production" and auth_mode != "required":
        errors.append("production_auth_mode_must_be_required")

    if effective_mode == "production":
        for key in ("AUTH_SECRET", "CONNECTOR_SECRET_KEY"):
            if is_placeholder(values.get(key, "")):
                errors.append(f"production_secret_not_set:{key}")
        cors = values.get("CORS_ORIGINS", "")
        if "*" in {part.strip() for part in cors.split(",")}:
            errors.append("production_cors_wildcard_forbidden")
        kms_provider = values.get("SECRET_KMS_PROVIDER", "local").strip().lower() or "local"
        kms_requirements = {
            "local": ("SECRET_KMS_KEY",),
            "vault_transit": ("VAULT_ADDR", "VAULT_TOKEN", "VAULT_TRANSIT_KEY"),
            "aws_kms": ("AWS_KMS_KEY_ID",),
            "gcp_kms": ("GCP_KMS_KEY_NAME",),
            "azure_key_vault": ("AZURE_KEY_VAULT_KEY_ID",),
        }
        if kms_provider not in kms_requirements:
            errors.append(f"unsupported_kms_provider:{kms_provider}")
        else:
            for key in kms_requirements[kms_provider]:
                if is_placeholder(values.get(key, "")):
                    errors.append(f"production_secret_not_set:{key}")
        if is_placeholder(values.get("POSTGRES_PASSWORD", "")):
            errors.append("production_secret_not_set:POSTGRES_PASSWORD")
        if values.get("DEMO_ACCOUNT_ENABLED", "false").strip().lower() == "true":
            errors.append("production_demo_account_must_be_disabled")
        password_min_length = int(values.get("PASSWORD_MIN_LENGTH", "8") or "8")
        if password_min_length < 8:
            errors.append("production_password_min_length_must_be_at_least_8")
        elif password_min_length < 15:
            warnings.append("production_password_length_below_recommended_15_without_mfa")
        password_scrypt_n = int(values.get("PASSWORD_SCRYPT_N", "131072") or "131072")
        password_scrypt_p = int(values.get("PASSWORD_SCRYPT_P", "1") or "1")
        if password_scrypt_n < 131072 and password_scrypt_p < 5:
            errors.append("production_scrypt_cost_below_security_baseline")
        if values.get("ANTIVIRUS_MODE", "").lower() != "required":
            errors.append("production_antivirus_mode_must_be_required")
        if values.get("METADATA_FALLBACK_SQLITE", "").lower() == "true":
            warnings.append("metadata_sqlite_fallback_enabled_in_production")
    else:
        for key in ("AUTH_SECRET", "CONNECTOR_SECRET_KEY"):
            if is_placeholder(values.get(key, "")):
                warnings.append(f"placeholder:{key}")

    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    if "name: datavision" not in compose:
        errors.append("compose_project_name_not_stable")
    for volume in ("postgres_data:", "redis_data:", "clamav_data:"):
        if volume not in compose:
            errors.append(f"missing_volume:{volume[:-1]}")

    return {
        "product": "DataVision AI",
        "product_version": version,
        "mode": effective_mode,
        "env_file": str(env_file),
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate DataVision configuration before install/upgrade.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--mode", choices=("development", "test", "staging", "production"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = root / env_file
    try:
        result = inspect(root, env_file, args.mode)
    except (OSError, ValueError) as exc:
        result = {"product": "DataVision AI", "status": "fail", "errors": [str(exc)], "warnings": []}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"CONFIG_DOCTOR: {result['status'].upper()}")
        for warning in result.get("warnings", []):
            print(f"WARN {warning}")
        for error in result.get("errors", []):
            print(f"FAIL {error}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
