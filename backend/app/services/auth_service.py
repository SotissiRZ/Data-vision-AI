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

from sqlalchemy import text

from app.core.config import get_settings
from app.services.metadata_store import connection, execute, fetch_all, fetch_one, slugify, utcnow
from app.services.session_security import register_session_posture, validate_session_security

ROLES = ["owner", "admin", "data_scientist", "analyst", "viewer"]
ROLE_PERMISSIONS = {
    "owner": {"workspace:manage", "members:manage", "dataset:read", "dataset:write", "analysis:run", "model:run", "publish:write", "audit:read", "jobs:manage", "policies:manage", "review:read", "review:comment", "review:submit", "review:approve", "review:manage", "certify:manage", "connectors:read", "connectors:manage", "refresh:run", "reliability:read", "reliability:manage", "reliability:run", "observability:read", "evaluation:manage", "actions:read", "actions:manage", "actions:trigger", "actions:approve", "plugins:read", "plugins:manage", "plugins:execute"},
    "admin": {"workspace:manage", "members:manage", "dataset:read", "dataset:write", "analysis:run", "model:run", "publish:write", "audit:read", "jobs:manage", "policies:manage", "review:read", "review:comment", "review:submit", "review:approve", "review:manage", "certify:manage", "connectors:read", "connectors:manage", "refresh:run", "reliability:read", "reliability:manage", "reliability:run", "observability:read", "evaluation:manage", "actions:read", "actions:manage", "actions:trigger", "actions:approve", "plugins:read", "plugins:manage", "plugins:execute"},
    "data_scientist": {"dataset:read", "dataset:write", "analysis:run", "model:run", "publish:write", "jobs:manage", "review:read", "review:comment", "review:submit", "review:approve", "connectors:read", "refresh:run", "reliability:read", "reliability:manage", "reliability:run", "observability:read", "evaluation:manage", "actions:read", "actions:trigger", "actions:approve", "plugins:read", "plugins:execute"},
    "analyst": {"dataset:read", "analysis:run", "publish:write", "review:read", "review:comment", "review:submit", "connectors:read", "reliability:read", "observability:read", "actions:read", "actions:trigger", "plugins:read", "plugins:execute"},
    "viewer": {"dataset:read", "review:read", "review:comment", "connectors:read", "reliability:read", "observability:read", "actions:read", "plugins:read"},
}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _scrypt_maxmem(n: int, r: int) -> int:
    """Return an explicit OpenSSL scrypt memory budget.

    OpenSSL 3 can enforce a relatively small implicit memory ceiling when
    ``maxmem`` is omitted. DataVision's default N=131072 / r=8 needs roughly
    128 MiB, which otherwise raises ``digital envelope routines: memory limit
    exceeded`` on a clean first-run installation. Keep a configurable floor and
    always add headroom above the algorithm's estimated working set.
    """
    settings = get_settings()
    configured = max(64, int(settings.password_scrypt_maxmem_mb)) * 1024 * 1024
    estimated = 128 * int(n) * int(r)
    return max(configured, estimated + 32 * 1024 * 1024)


def hash_password(password: str) -> str:
    settings = get_settings()
    minimum = max(8, int(settings.password_min_length))
    if len(password) < minimum:
        raise ValueError(f"Le mot de passe doit contenir au moins {minimum} caractères.")
    salt = os.urandom(16)
    n = max(2**14, int(settings.password_scrypt_n))
    r = max(8, int(settings.password_scrypt_r))
    p = max(1, int(settings.password_scrypt_p))
    key = hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=32,
        maxmem=_scrypt_maxmem(n, r),
    )
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        n_i, r_i, p_i = int(n), int(r), int(p)
        key = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=n_i, r=r_i, p=p_i, dklen=32,
            maxmem=_scrypt_maxmem(n_i, r_i),
        )
        return hmac.compare_digest(_b64(key), expected)
    except Exception:
        return False


def _token_secret() -> bytes:
    settings = get_settings()
    return settings.auth_secret.encode()


def issue_token(user_id: str, email: str, session_id: str | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "iss": "datavision-ai",
        **({"sid": session_id} if session_id else {}),
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
    if payload.get("iss") != "datavision-ai":
        raise ValueError("Émetteur du token invalide")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if int(payload.get("exp", 0)) < now_ts:
        raise ValueError("Token expiré")
    if int(payload.get("iat", 0)) > now_ts + 60:
        raise ValueError("Horodatage du token invalide")
    if not payload.get("sub"):
        raise ValueError("Sujet du token manquant")
    return payload


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def validate_session_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Validate persistent session state when the access token carries a session id.

    Tokens created before v2.12 may not contain ``sid``; they remain valid until their normal
    expiration to avoid breaking an in-place upgrade. New sessions are revocable server-side.
    """
    sid = str(payload.get("sid") or "")
    if not sid:
        return None
    row = fetch_one("SELECT * FROM auth_sessions WHERE id=:id", {"id": sid})
    if not row or row.get("revoked_at"):
        raise ValueError("Session révoquée")
    exp = _parse_dt(row.get("expires_at"))
    if not exp or exp <= datetime.now(timezone.utc):
        raise ValueError("Session expirée")
    if str(row.get("user_id")) != str(payload.get("sub") or ""):
        raise ValueError("Session incohérente")
    validate_session_security(str(row["user_id"]), sid, row)
    execute("UPDATE auth_sessions SET last_seen_at=:now WHERE id=:id", {"now": utcnow(), "id": sid})
    return row




def _login_principal_hash(email: str, client_key: str) -> str:
    material = f"{email.strip().lower()}|{client_key.strip().lower()}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def enforce_login_throttle(email: str, client_key: str) -> None:
    settings = get_settings()
    principal = _login_principal_hash(email, client_key)
    row = fetch_one("SELECT failures,window_started_at,locked_until FROM auth_login_throttle WHERE principal_hash=:p", {"p": principal})
    if not row:
        return
    locked_until = _parse_dt(row.get("locked_until"))
    if locked_until and locked_until > datetime.now(timezone.utc):
        remaining = max(1, int((locked_until - datetime.now(timezone.utc)).total_seconds() // 60) + 1)
        raise PermissionError(f"Trop de tentatives de connexion. Réessayez dans environ {remaining} minute(s).")


def record_login_failure(email: str, client_key: str) -> None:
    settings = get_settings()
    principal = _login_principal_hash(email, client_key)
    now = datetime.now(timezone.utc)
    row = fetch_one("SELECT failures,window_started_at,locked_until FROM auth_login_throttle WHERE principal_hash=:p", {"p": principal})
    window_minutes = max(1, int(settings.auth_login_lockout_minutes))
    failures = 1
    window_started = now
    if row:
        started = _parse_dt(row.get("window_started_at"))
        if started and (now - started) <= timedelta(minutes=window_minutes):
            failures = int(row.get("failures") or 0) + 1
            window_started = started
    locked_until = None
    if failures >= max(1, int(settings.auth_login_max_failures)):
        locked_until = now + timedelta(minutes=window_minutes)
    execute(
        """INSERT INTO auth_login_throttle(principal_hash,failures,window_started_at,locked_until,updated_at)
           VALUES(:p,:f,:w,:l,:u)
           ON CONFLICT(principal_hash) DO UPDATE SET failures=:f,window_started_at=:w,locked_until=:l,updated_at=:u""",
        {"p": principal, "f": failures, "w": window_started.isoformat(), "l": locked_until.isoformat() if locked_until else None, "u": now.isoformat()},
    )


def clear_login_failures(email: str, client_key: str) -> None:
    principal = _login_principal_hash(email, client_key)
    execute("DELETE FROM auth_login_throttle WHERE principal_hash=:p", {"p": principal})


def create_authenticated_session(user_id: str, email: str, *, provider: str = "local", device_label: str = "", user_agent: str = "", mfa_verified: bool = False) -> dict[str, Any]:
    settings = get_settings()
    sid = str(uuid.uuid4())
    refresh_token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=max(1, settings.refresh_token_days))
    execute(
        """INSERT INTO auth_sessions(id,user_id,provider,refresh_token_hash,device_label,user_agent,created_at,last_seen_at,expires_at)
           VALUES(:id,:user,:provider,:refresh,:device,:ua,:created,:seen,:expires)""",
        {"id": sid, "user": user_id, "provider": provider, "refresh": _hash_refresh_token(refresh_token),
         "device": (device_label or "")[:160], "ua": (user_agent or "")[:1000],
         "created": now.isoformat(), "seen": now.isoformat(), "expires": expires.isoformat()},
    )
    try:
        posture = register_session_posture(
            user_id, sid, user_agent=user_agent, device_label=device_label, mfa_verified=mfa_verified
        )
    except Exception:
        execute("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": sid})
        raise
    return {
        "access_token": issue_token(user_id, email, sid),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(settings.access_token_minutes * 60),
        "session_id": sid,
        "session_posture": posture,
    }


def refresh_authenticated_session(refresh_token: str) -> dict[str, Any]:
    token_hash = _hash_refresh_token(refresh_token.strip())
    row = fetch_one("SELECT * FROM auth_sessions WHERE refresh_token_hash=:h", {"h": token_hash})
    if not row or row.get("revoked_at"):
        raise ValueError("Refresh token invalide ou révoqué")
    exp = _parse_dt(row.get("expires_at"))
    if not exp or exp <= datetime.now(timezone.utc):
        raise ValueError("Session expirée")
    validate_session_security(str(row["user_id"]), str(row["id"]), row)
    user = get_user(str(row["user_id"]))
    if not user or not user.get("is_active"):
        raise ValueError("Utilisateur introuvable ou inactif")
    next_refresh = secrets.token_urlsafe(48)
    now = utcnow()
    execute(
        "UPDATE auth_sessions SET refresh_token_hash=:h,last_seen_at=:now,rotated_at=:now WHERE id=:id",
        {"h": _hash_refresh_token(next_refresh), "now": now, "id": row["id"]},
    )
    return {
        "access_token": issue_token(user["id"], user["email"], str(row["id"])),
        "refresh_token": next_refresh,
        "token_type": "bearer",
        "expires_in": int(get_settings().access_token_minutes * 60),
        "session_id": str(row["id"]),
        "user": user,
    }


def list_user_sessions(user_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id,provider,device_label,user_agent,created_at,last_seen_at,expires_at,revoked_at,rotated_at FROM auth_sessions WHERE user_id=:u ORDER BY created_at DESC",
        {"u": user_id},
    )
    for row in rows:
        row["active"] = not bool(row.get("revoked_at")) and bool(_parse_dt(row.get("expires_at")) and _parse_dt(row.get("expires_at")) > datetime.now(timezone.utc))
    return rows


def revoke_user_session(user_id: str, session_id: str) -> None:
    row = fetch_one("SELECT user_id FROM auth_sessions WHERE id=:id", {"id": session_id})
    if not row or str(row.get("user_id")) != str(user_id):
        raise KeyError("Session introuvable")
    execute("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": session_id})


def revoke_all_user_sessions(user_id: str, *, except_session_id: str | None = None) -> int:
    rows = fetch_all("SELECT id FROM auth_sessions WHERE user_id=:u AND revoked_at IS NULL", {"u": user_id})
    count = 0
    for row in rows:
        if except_session_id and row["id"] == except_session_id:
            continue
        execute("UPDATE auth_sessions SET revoked_at=:now WHERE id=:id", {"now": utcnow(), "id": row["id"]})
        count += 1
    return count


def get_user(user_id: str) -> dict[str, Any] | None:
    return fetch_one("SELECT id,email,display_name,is_active,created_at FROM users WHERE id=:id", {"id": user_id})


def get_user_by_email(email: str) -> dict[str, Any] | None:
    return fetch_one("SELECT * FROM users WHERE lower(email)=lower(:email)", {"email": email.strip()})


def user_count() -> int:
    row = fetch_one("SELECT COUNT(*) AS n FROM users")
    return int(row["n"]) if row else 0


def owner_count() -> int:
    row = fetch_one("SELECT COUNT(*) AS n FROM organization_members WHERE role='owner'")
    return int(row["n"]) if row else 0


def demo_account_enabled() -> bool:
    settings = get_settings()
    return bool(settings.demo_account_enabled and settings.app_env.lower() in {"development", "test"})


def ensure_demo_account() -> dict[str, Any] | None:
    """Provision a development-only demo user and isolated workspace.

    The demo account is never provisioned when APP_ENV=production, even if the
    environment variable is accidentally enabled. It uses the configured
    credentials only for local/test convenience and is kept out of the owner
    bootstrap lifecycle.
    """
    if not demo_account_enabled():
        return None
    settings = get_settings()
    email = settings.demo_account_email.strip().lower()
    password = settings.demo_account_password
    display_name = settings.demo_account_display_name.strip() or "Utilisateur Démo"
    organization_name = settings.demo_account_organization.strip() or "DataVision Démo"
    if not email:
        raise ValueError("DEMO_ACCOUNT_EMAIL est requis lorsque le compte démo est activé.")
    if len(password) < max(8, int(settings.password_min_length)):
        raise ValueError("DEMO_ACCOUNT_PASSWORD ne respecte pas la longueur minimale configurée.")

    now = utcnow()
    user = get_user_by_email(email)
    if user is None:
        user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"datavision-demo-user:{email}"))
        execute(
            "INSERT INTO users(id,email,password_hash,display_name,is_active,created_at) VALUES(:id,:email,:pw,:name,1,:created)",
            {"id": user_id, "email": email, "pw": hash_password(password), "name": display_name, "created": now},
        )
    else:
        user_id = str(user["id"])
        if verify_password(password, str(user.get("password_hash") or "")):
            execute(
                "UPDATE users SET display_name=:name,is_active=1 WHERE id=:id",
                {"name": display_name, "id": user_id},
            )
        else:
            execute(
                "UPDATE users SET password_hash=:pw,display_name=:name,is_active=1 WHERE id=:id",
                {"pw": hash_password(password), "name": display_name, "id": user_id},
            )

    org_slug = "datavision-demo"
    org = fetch_one("SELECT id FROM organizations WHERE slug=:slug", {"slug": org_slug})
    if org is None:
        org_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "datavision-demo-organization"))
        execute(
            "INSERT INTO organizations(id,name,slug,created_at) VALUES(:id,:name,:slug,:created)",
            {"id": org_id, "name": organization_name, "slug": org_slug, "created": now},
        )
    else:
        org_id = str(org["id"])

    execute(
        "INSERT INTO organization_members(organization_id,user_id,role,created_at) VALUES(:org,:user,'admin',:created) ON CONFLICT (organization_id,user_id) DO NOTHING",
        {"org": org_id, "user": user_id, "created": now},
    )

    workspace_slug = "demo"
    workspace = fetch_one(
        "SELECT id FROM workspaces WHERE organization_id=:org AND slug=:slug",
        {"org": org_id, "slug": workspace_slug},
    )
    if workspace is None:
        workspace_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "datavision-demo-workspace"))
        execute(
            "INSERT INTO workspaces(id,organization_id,name,slug,created_by,created_at) VALUES(:id,:org,'Workspace Démo',:slug,:user,:created)",
            {"id": workspace_id, "org": org_id, "slug": workspace_slug, "user": user_id, "created": now},
        )
    else:
        workspace_id = str(workspace["id"])

    execute(
        "INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(:ws,:user,'admin',:created) ON CONFLICT (workspace_id,user_id) DO NOTHING",
        {"ws": workspace_id, "user": user_id, "created": now},
    )
    return {
        "enabled": True,
        "email": email,
        "password": password,
        "display_name": display_name,
        "workspace_id": workspace_id,
        "role": "admin",
    }



def register_account(email: str, password: str, display_name: str, organization_name: str = "") -> dict[str, Any]:
    """Create a self-service DataVision tenant account atomically.

    A standard sign-up creates an isolated organization and primary workspace and
    makes the new user owner of that tenant. Deployments that do not want public
    registration can disable SELF_REGISTRATION_ENABLED while keeping login and
    the secure first-run bootstrap available.
    """
    settings = get_settings()
    if not settings.self_registration_enabled:
        raise PermissionError("L’inscription libre est désactivée sur cette installation.")

    normalized_email = email.strip().lower()
    if len(normalized_email) < 3 or "@" not in normalized_email or normalized_email.startswith("@") or normalized_email.endswith("@"):
        raise ValueError("Adresse email invalide.")
    if get_user_by_email(normalized_email):
        raise ValueError("Un compte existe déjà avec cette adresse email. Utilisez la connexion.")

    clean_name = display_name.strip() or normalized_email.split("@", 1)[0]
    clean_org = organization_name.strip() or f"Espace de {clean_name}"
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    now = utcnow()
    pw = hash_password(password)

    base_slug = slugify(clean_org)
    with connection() as conn:
        existing_user = conn.execute(
            text("SELECT id FROM users WHERE lower(email)=lower(:email)"), {"email": normalized_email}
        ).mappings().first()
        if existing_user:
            raise ValueError("Un compte existe déjà avec cette adresse email. Utilisez la connexion.")
        existing_org = conn.execute(
            text("SELECT id FROM organizations WHERE slug=:slug"), {"slug": base_slug}
        ).mappings().first()
        org_slug = f"{base_slug[:68]}-{org_id[:8]}" if existing_org else base_slug
        conn.execute(
            text("INSERT INTO users(id,email,password_hash,display_name,is_active,created_at) VALUES(:id,:email,:pw,:name,1,:created)"),
            {"id": user_id, "email": normalized_email, "pw": pw, "name": clean_name, "created": now},
        )
        conn.execute(
            text("INSERT INTO organizations(id,name,slug,created_at) VALUES(:id,:name,:slug,:created)"),
            {"id": org_id, "name": clean_org, "slug": org_slug, "created": now},
        )
        conn.execute(
            text("INSERT INTO organization_members(organization_id,user_id,role,created_at) VALUES(:org,:user,'owner',:created)"),
            {"org": org_id, "user": user_id, "created": now},
        )
        conn.execute(
            text("INSERT INTO workspaces(id,organization_id,name,slug,created_by,created_at) VALUES(:id,:org,'Workspace principal','principal',:user,:created)"),
            {"id": workspace_id, "org": org_id, "user": user_id, "created": now},
        )
        conn.execute(
            text("INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(:ws,:user,'owner',:created)"),
            {"ws": workspace_id, "user": user_id, "created": now},
        )

    auth = create_authenticated_session(user_id, normalized_email, provider="local", device_label="signup")
    return {**auth, "user": get_user(user_id), "organization_id": org_id, "workspace_id": workspace_id}


def bootstrap(email: str, password: str, display_name: str, organization_name: str) -> dict[str, Any]:
    if owner_count() > 0:
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
    auth = create_authenticated_session(user_id, email.strip().lower(), provider="local", device_label="bootstrap")
    return {**auth, "user": get_user(user_id), "organization_id": org_id, "workspace_id": workspace_id}


def login(email: str, password: str) -> dict[str, Any]:
    row = get_user_by_email(email)
    if not row or not row.get("is_active") or not verify_password(password, row["password_hash"]):
        raise ValueError("Email ou mot de passe incorrect.")
    auth = create_authenticated_session(row["id"], row["email"], provider="local", device_label="password")
    return {**auth, "user": get_user(row["id"])}


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
