from __future__ import annotations

import hmac
import ipaddress
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Request

from app.core.config import get_settings

COOKIE_NAME = "dv_first_run_setup"
SETUP_TTL_SECONDS = 15 * 60
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _token_path() -> Path:
    settings = get_settings()
    root = Path(settings.data_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / ".first_run_setup.json"


def _client_is_local_or_private(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_private
    except ValueError:
        # FastAPI TestClient uses a symbolic host. Permit it only outside production.
        return get_settings().app_env.lower() != "production" and host in {"testclient", "localhost"}


def _origin_is_local(request: Request) -> bool:
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return False
    try:
        hostname = (urlparse(origin).hostname or "").lower()
    except Exception:
        return False
    return hostname in _LOCAL_HOSTS


def local_first_run_allowed(request: Request) -> bool:
    """Allow browser bootstrap only from a local DataVision installation.

    In production, a remote/server deployment must create the first owner from the
    server-side CLI. This avoids exposing a public "first user wins" endpoint while
    keeping the desktop/local first-run experience simple.
    """
    settings = get_settings()
    if settings.first_run_setup_mode == "disabled":
        return False
    if settings.first_run_setup_mode != "local":
        return False
    return _origin_is_local(request) and _client_is_local_or_private(request)


def issue_setup_token() -> str:
    token = secrets.token_urlsafe(48)
    payload = {"token": token, "expires_at": int(time.time()) + SETUP_TTL_SECONDS}
    path = _token_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)
    return token


def validate_setup_token(candidate: str | None) -> bool:
    if not candidate:
        return False
    path = _token_path()
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("expires_at", 0)) < int(time.time()):
            invalidate_setup_token()
            return False
        expected = str(payload.get("token", ""))
        return bool(expected) and hmac.compare_digest(candidate, expected)
    except Exception:
        invalidate_setup_token()
        return False


def invalidate_setup_token() -> None:
    try:
        _token_path().unlink(missing_ok=True)
    except OSError:
        pass
