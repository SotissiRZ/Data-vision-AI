from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.services.metadata_store import execute, fetch_all, fetch_one, slugify, utcnow

ROLES = ["owner", "admin", "data_scientist", "analyst", "viewer"]
ROLE_PERMISSIONS = {
    "owner": {"workspace:manage", "members:manage", "dataset:read", "dataset:write", "analysis:run", "model:run", "publish:write", "audit:read", "jobs:manage", "policies:manage", "review:read", "review:comment", "review:submit", "review:approve", "review:manage", "certify:manage", "connectors:read", "connectors:manage", "refresh:run", "reliability:read", "reliability:manage", "reliability:run", "observability:read", "evaluation:manage", "actions:read", "actions:manage", "actions:trigger", "actions:approve"},
    "admin": {"workspace:manage", "members:manage", "dataset:read", "dataset:write", "analysis:run", "model:run", "publish:write", "audit:read", "jobs:manage", "policies:manage", "review:read", "review:comment", "review:submit", "review:approve", "review:manage", "certify:manage", "connectors:read", "connectors:manage", "refresh:run", "reliability:read", "reliability:manage", "reliability:run", "observability:read", "evaluation:manage", "actions:read", "actions:manage", "actions:trigger", "actions:approve"},
    "data_scientist": {"dataset:read", "dataset:write", "analysis:run", "model:run", "publish:write", "jobs:manage", "review:read", "review:comment", "review:submit", "review:approve", "connectors:read", "refresh:run", "reliability:read", "reliability:manage", "reliability:run", "observability:read", "evaluation:manage", "actions:read", "actions:trigger", "actions:approve"},
    "analyst": {"dataset:read", "analysis:run", "publish:write", "review:read", "review:comment", "review:submit", "connectors:read", "reliability:read", "observability:read", "actions:read", "actions:trigger"},
    "viewer": {"dataset:read", "review:read", "review:comment", "connectors:read", "reliability:read", "observability:read", "actions:read"},
}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
    salt = os.urandom(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_b64(salt)}${_b64(key)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        key = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(_b64(key), expected)
    except Exception:
        return False


def _token_secret() -> bytes:
    settings = get_settings()
    return settings.auth_secret.encode()


def issue_token(user_id: str, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "iss": "datavision-ai",
    }
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64(json.dumps(header, separators=(",", ":")).encode())
    p = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_token_secret(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


def decode_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Token invalide")
    h, p, sig = parts
    expected = _b64(hmac.new(_token_secret(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Signature du token invalide")
    payload = json.loads(_unb64(p))
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Token expiré")
    return payload


def get_user(user_id: str) -> dict[str, Any] | None:
    return fetch_one("SELECT id,email,display_name,is_active,created_at FROM users WHERE id=:id", {"id": user_id})


def get_user_by_email(email: str) -> dict[str, Any] | None:
    return fetch_one("SELECT * FROM users WHERE lower(email)=lower(:email)", {"email": email.strip()})


def user_count() -> int:
    row = fetch_one("SELECT COUNT(*) AS n FROM users")
    return int(row["n"]) if row else 0


def bootstrap(email: str, password: str, display_name: str, organization_name: str) -> dict[str, Any]:
    if user_count() > 0:
        raise ValueError("Le bootstrap a déjà été effectué. Utilisez la connexion.")
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    now = utcnow()
    pw = hash_password(password)
    org_slug = slugify(organization_name)
    execute("INSERT INTO users(id,email,password_hash,display_name,is_active,created_at) VALUES(:id,:email,:pw,:name,1,:created)", {"id": user_id, "email": email.strip().lower(), "pw": pw, "name": display_name.strip() or email.split("@")[0], "created": now})
    execute("INSERT INTO organizations(id,name,slug,created_at) VALUES(:id,:name,:slug,:created)", {"id": org_id, "name": organization_name.strip() or "Organisation", "slug": org_slug, "created": now})
    execute("INSERT INTO organization_members(organization_id,user_id,role,created_at) VALUES(:org,:user,'owner',:created)", {"org": org_id, "user": user_id, "created": now})
    execute("INSERT INTO workspaces(id,organization_id,name,slug,created_by,created_at) VALUES(:id,:org,'Workspace principal','principal',:user,:created)", {"id": workspace_id, "org": org_id, "user": user_id, "created": now})
    execute("INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(:ws,:user,'owner',:created)", {"ws": workspace_id, "user": user_id, "created": now})
    token = issue_token(user_id, email.strip().lower())
    return {"access_token": token, "token_type": "bearer", "user": get_user(user_id), "organization_id": org_id, "workspace_id": workspace_id}


def login(email: str, password: str) -> dict[str, Any]:
    row = get_user_by_email(email)
    if not row or not row.get("is_active") or not verify_password(password, row["password_hash"]):
        raise ValueError("Email ou mot de passe incorrect.")
    token = issue_token(row["id"], row["email"])
    return {"access_token": token, "token_type": "bearer", "user": get_user(row["id"])}


def organizations_for_user(user_id: str) -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT o.id,o.name,o.slug,o.created_at,m.role
        FROM organizations o JOIN organization_members m ON m.organization_id=o.id
        WHERE m.user_id=:user ORDER BY o.name
    """, {"user": user_id})


def workspaces_for_user(user_id: str) -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT w.id,w.organization_id,w.name,w.slug,w.created_at,wm.role
        FROM workspaces w JOIN workspace_members wm ON wm.workspace_id=w.id
        WHERE wm.user_id=:user ORDER BY w.name
    """, {"user": user_id})


def workspace_role(user_id: str, workspace_id: str) -> str | None:
    row = fetch_one("SELECT role FROM workspace_members WHERE workspace_id=:ws AND user_id=:user", {"ws": workspace_id, "user": user_id})
    return row["role"] if row else None


def has_permission(user_id: str, workspace_id: str, permission: str) -> bool:
    role = workspace_role(user_id, workspace_id)
    return bool(role and permission in ROLE_PERMISSIONS.get(role, set()))


def session_payload(user_id: str) -> dict[str, Any]:
    user = get_user(user_id)
    if not user:
        raise ValueError("Utilisateur introuvable")
    return {
        "user": user,
        "organizations": organizations_for_user(user_id),
        "workspaces": workspaces_for_user(user_id),
        "roles": ROLES,
    }
