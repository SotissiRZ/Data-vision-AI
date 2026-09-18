from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.config import get_settings
from app.services.auth_service import (
    ROLES,
    create_authenticated_session,
    get_user,
    get_user_by_email,
    hash_password,
)
from app.services.connector_service import decrypt_secret, encrypt_secret
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _validate_external_url(url: str, *, resolve_dns: bool = False) -> None:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("URL externe invalide")
    settings = get_settings()
    dev_local = settings.app_env == "development" and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not dev_local:
        raise ValueError("HTTPS est requis pour les fournisseurs d'identité externes")
    if parsed.username or parsed.password:
        raise ValueError("Credentials intégrés dans l'URL interdits")
    if resolve_dns and not dev_local:
        try:
            infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("Résolution DNS impossible") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ValueError("Endpoint OIDC vers une adresse privée/réservée refusé")


def _provider_row(row: dict[str, Any], *, public: bool = False) -> dict[str, Any]:
    out = dict(row)
    out["scopes"] = json_loads(out.pop("scopes_json", "[]"), [])
    out["allowed_domains"] = json_loads(out.pop("allowed_domains_json", "[]"), [])
    out.pop("client_secret_ciphertext", None)
    out["has_client_secret"] = bool(row.get("client_secret_ciphertext"))
    if public:
        keep = {"id", "name", "enabled"}
        out = {k: v for k, v in out.items() if k in keep}
    return out


def discover_oidc(issuer: str) -> dict[str, Any]:
    issuer = issuer.rstrip("/")
    _validate_external_url(issuer, resolve_dns=True)
    url = issuer + "/.well-known/openid-configuration"
    with httpx.Client(timeout=8.0, follow_redirects=False) as client:
        res = client.get(url, headers={"Accept": "application/json", "User-Agent": "DataVision-Identity/2.12"})
        res.raise_for_status()
        data = res.json()
    required = ["issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"]
    if any(not data.get(k) for k in required):
        raise ValueError("Discovery OIDC incomplète")
    if str(data["issuer"]).rstrip("/") != issuer:
        raise ValueError("Issuer OIDC incohérent avec la discovery")
    for key in ["authorization_endpoint", "token_endpoint", "jwks_uri"]:
        _validate_external_url(str(data[key]), resolve_dns=False)
    return {k: data.get(k) for k in required}


def create_oidc_provider(
    actor_id: str,
    workspace_id: str,
    *,
    name: str,
    issuer: str,
    client_id: str,
    client_secret: str,
    authorization_endpoint: str | None = None,
    token_endpoint: str | None = None,
    jwks_uri: str | None = None,
    scopes: list[str] | None = None,
    allowed_domains: list[str] | None = None,
    default_role: str = "viewer",
    email_claim: str = "email",
    name_claim: str = "name",
    groups_claim: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    if default_role not in ROLES:
        raise ValueError("Rôle par défaut invalide")
    ws = fetch_one("SELECT organization_id FROM workspaces WHERE id=:id", {"id": workspace_id})
    if not ws:
        raise KeyError("Workspace introuvable")
    issuer = issuer.rstrip("/")
    _validate_external_url(issuer, resolve_dns=False)
    if not authorization_endpoint or not token_endpoint or not jwks_uri:
        discovered = discover_oidc(issuer)
        authorization_endpoint = authorization_endpoint or str(discovered["authorization_endpoint"])
        token_endpoint = token_endpoint or str(discovered["token_endpoint"])
        jwks_uri = jwks_uri or str(discovered["jwks_uri"])
    for endpoint in [authorization_endpoint, token_endpoint, jwks_uri]:
        _validate_external_url(str(endpoint), resolve_dns=False)
    pid = str(uuid.uuid4())
    now = utcnow()
    execute(
        """INSERT INTO oidc_providers(id,organization_id,workspace_id,name,issuer,client_id,client_secret_ciphertext,authorization_endpoint,token_endpoint,jwks_uri,scopes_json,email_claim,name_claim,groups_claim,allowed_domains_json,default_role,enabled,created_by,created_at,updated_at)
           VALUES(:id,:org,:ws,:name,:issuer,:client,:secret,:auth,:token,:jwks,:scopes,:email_claim,:name_claim,:groups_claim,:domains,:role,:enabled,:user,:now,:now)""",
        {
            "id": pid,
            "org": ws["organization_id"],
            "ws": workspace_id,
            "name": name.strip(),
            "issuer": issuer,
            "client": client_id.strip(),
            "secret": encrypt_secret(client_secret),
            "auth": str(authorization_endpoint),
            "token": str(token_endpoint),
            "jwks": str(jwks_uri),
            "scopes": json_dumps(scopes or ["openid", "profile", "email"]),
            "email_claim": email_claim or "email",
            "name_claim": name_claim or "name",
            "groups_claim": groups_claim,
            "domains": json_dumps([d.strip().lower().lstrip("@") for d in (allowed_domains or []) if d.strip()]),
            "role": default_role,
            "enabled": 1 if enabled else 0,
            "user": actor_id,
            "now": now,
        },
    )
    return get_oidc_provider(workspace_id, pid)


def get_oidc_provider(workspace_id: str, provider_id: str, *, include_secret: bool = False) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM oidc_providers WHERE id=:id AND workspace_id=:ws", {"id": provider_id, "ws": workspace_id})
    if not row:
        raise KeyError("Fournisseur OIDC introuvable")
    if include_secret:
        out = dict(row)
        out["client_secret"] = decrypt_secret(out.get("client_secret_ciphertext"))
        out["scopes"] = json_loads(out.get("scopes_json"), [])
        out["allowed_domains"] = json_loads(out.get("allowed_domains_json"), [])
        return out
    return _provider_row(row)


def list_oidc_providers(workspace_id: str) -> list[dict[str, Any]]:
    return [_provider_row(r) for r in fetch_all("SELECT * FROM oidc_providers WHERE workspace_id=:ws ORDER BY name", {"ws": workspace_id})]


def list_public_oidc_providers() -> list[dict[str, Any]]:
    return [_provider_row(r, public=True) for r in fetch_all("SELECT * FROM oidc_providers WHERE enabled=1 ORDER BY name")]


def delete_oidc_provider(workspace_id: str, provider_id: str) -> None:
    row = fetch_one("SELECT id FROM oidc_providers WHERE id=:id AND workspace_id=:ws", {"id": provider_id, "ws": workspace_id})
    if not row:
        raise KeyError("Fournisseur OIDC introuvable")
    execute("UPDATE oidc_providers SET enabled=0,updated_at=:now WHERE id=:id", {"now": utcnow(), "id": provider_id})


def oidc_start(provider_id: str, redirect_uri: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM oidc_providers WHERE id=:id AND enabled=1", {"id": provider_id})
    if not row:
        raise KeyError("Fournisseur SSO introuvable ou désactivé")
    settings = get_settings()
    allowed_frontend = settings.frontend_url.rstrip("/")
    if not redirect_uri.startswith(allowed_frontend):
        raise ValueError("redirect_uri non autorisée")
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=max(2, settings.oidc_state_minutes))
    execute(
        """INSERT INTO oidc_login_states(state_hash,provider_id,code_verifier_ciphertext,redirect_uri,nonce_hash,created_at,expires_at)
           VALUES(:state,:provider,:verifier,:redirect,:nonce,:created,:expires)""",
        {"state": _hash(state), "provider": provider_id, "verifier": encrypt_secret(verifier), "redirect": redirect_uri,
         "nonce": _hash(nonce), "created": now.isoformat(), "expires": expires.isoformat()},
    )
    scopes = json_loads(row.get("scopes_json"), ["openid", "profile", "email"])
    params = {
        "response_type": "code",
        "client_id": row["client_id"],
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {"authorization_url": str(row["authorization_endpoint"]) + ("&" if "?" in str(row["authorization_endpoint"]) else "?") + urlencode(params), "state": state, "provider": _provider_row(row, public=True)}


def _verify_id_token(id_token: str, provider: dict[str, Any], expected_nonce_hash: str) -> dict[str, Any]:
    parts = id_token.split(".")
    if len(parts) != 3:
        raise ValueError("id_token OIDC invalide")
    header = json.loads(_b64decode(parts[0]))
    claims = json.loads(_b64decode(parts[1]))
    if header.get("alg") != "RS256":
        raise ValueError("Seul RS256 est accepté pour id_token")
    kid = str(header.get("kid") or "")
    _validate_external_url(str(provider["jwks_uri"]), resolve_dns=True)
    with httpx.Client(timeout=8.0, follow_redirects=False) as client:
        res = client.get(str(provider["jwks_uri"]), headers={"Accept": "application/json", "User-Agent": "DataVision-Identity/2.12"})
        res.raise_for_status()
        jwks = res.json()
    key = next((k for k in jwks.get("keys", []) if str(k.get("kid")) == kid and k.get("kty") == "RSA"), None)
    if not key:
        raise ValueError("Clé JWKS OIDC introuvable")
    n = int.from_bytes(_b64decode(str(key["n"])), "big")
    e = int.from_bytes(_b64decode(str(key["e"])), "big")
    public_key = rsa.RSAPublicNumbers(e, n).public_key()
    public_key.verify(_b64decode(parts[2]), f"{parts[0]}.{parts[1]}".encode(), padding.PKCS1v15(), hashes.SHA256())
    now = int(datetime.now(timezone.utc).timestamp())
    if int(claims.get("exp") or 0) <= now:
        raise ValueError("id_token expiré")
    if str(claims.get("iss") or "").rstrip("/") != str(provider["issuer"]).rstrip("/"):
        raise ValueError("Issuer id_token invalide")
    aud = claims.get("aud")
    auds = aud if isinstance(aud, list) else [aud]
    if provider["client_id"] not in auds:
        raise ValueError("Audience id_token invalide")
    if _hash(str(claims.get("nonce") or "")) != expected_nonce_hash:
        raise ValueError("Nonce OIDC invalide")
    return claims


def oidc_exchange(provider_id: str, code: str, state: str, redirect_uri: str) -> dict[str, Any]:
    state_hash = _hash(state)
    state_row = fetch_one("SELECT * FROM oidc_login_states WHERE state_hash=:s AND provider_id=:p", {"s": state_hash, "p": provider_id})
    if not state_row or state_row.get("used_at"):
        raise ValueError("State OIDC invalide ou déjà utilisé")
    exp = _parse_dt(state_row.get("expires_at"))
    if not exp or exp <= datetime.now(timezone.utc):
        raise ValueError("State OIDC expiré")
    if str(state_row.get("redirect_uri")) != redirect_uri:
        raise ValueError("redirect_uri incohérente")
    provider = fetch_one("SELECT * FROM oidc_providers WHERE id=:id AND enabled=1", {"id": provider_id})
    if not provider:
        raise KeyError("Fournisseur OIDC introuvable")
    _validate_external_url(str(provider["token_endpoint"]), resolve_dns=True)
    verifier = decrypt_secret(state_row.get("code_verifier_ciphertext"))
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": provider["client_id"],
        "code_verifier": verifier,
    }
    secret = decrypt_secret(provider.get("client_secret_ciphertext"))
    if secret:
        data["client_secret"] = secret
    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        res = client.post(str(provider["token_endpoint"]), data=data, headers={"Accept": "application/json", "User-Agent": "DataVision-Identity/2.12"})
        res.raise_for_status()
        token_payload = res.json()
    id_token = str(token_payload.get("id_token") or "")
    if not id_token:
        raise ValueError("Le fournisseur OIDC n'a pas retourné id_token")
    claims = _verify_id_token(id_token, provider, str(state_row["nonce_hash"]))
    subject = str(claims.get("sub") or "")
    email = str(claims.get(provider.get("email_claim") or "email") or "").strip().lower()
    if not subject or not email or "@" not in email:
        raise ValueError("Claims sub/email requis")
    domains = json_loads(provider.get("allowed_domains_json"), [])
    if domains and email.rsplit("@", 1)[-1].lower() not in set(domains):
        raise PermissionError("Domaine email non autorisé pour ce fournisseur SSO")
    identity = fetch_one("SELECT * FROM external_identities WHERE provider_id=:p AND subject=:s", {"p": provider_id, "s": subject})
    if identity:
        user = get_user(identity["user_id"])
    else:
        user = get_user_by_email(email)
        if not user:
            uid = str(uuid.uuid4())
            display = str(claims.get(provider.get("name_claim") or "name") or email.split("@", 1)[0])[:120]
            execute(
                "INSERT INTO users(id,email,password_hash,display_name,is_active,created_at) VALUES(:id,:email,:pw,:name,1,:now)",
                {"id": uid, "email": email, "pw": hash_password(secrets.token_urlsafe(32)), "name": display, "now": utcnow()},
            )
            user = get_user(uid)
        assert user is not None
        now = utcnow()
        execute("INSERT INTO external_identities(provider_id,subject,user_id,email,created_at,last_login_at) VALUES(:p,:s,:u,:e,:now,:now)", {"p": provider_id, "s": subject, "u": user["id"], "e": email, "now": now})
    assert user is not None
    role = str(provider.get("default_role") or "viewer")
    org_member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:u", {"org": provider["organization_id"], "u": user["id"]})
    if not org_member:
        execute("INSERT INTO organization_members(organization_id,user_id,role,created_at) VALUES(:org,:u,:role,:now)", {"org": provider["organization_id"], "u": user["id"], "role": role, "now": utcnow()})
    ws_member = fetch_one("SELECT role FROM workspace_members WHERE workspace_id=:ws AND user_id=:u", {"ws": provider["workspace_id"], "u": user["id"]})
    if not ws_member:
        execute("INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(:ws,:u,:role,:now)", {"ws": provider["workspace_id"], "u": user["id"], "role": role, "now": utcnow()})
    execute("UPDATE external_identities SET last_login_at=:now,email=:e WHERE provider_id=:p AND subject=:s", {"now": utcnow(), "e": email, "p": provider_id, "s": subject})
    execute("UPDATE oidc_login_states SET used_at=:now WHERE state_hash=:s", {"now": utcnow(), "s": state_hash})
    auth = create_authenticated_session(user["id"], user["email"], provider=f"oidc:{provider_id}", device_label=f"SSO {provider['name']}")
    return {**auth, "user": user, "workspace_id": provider["workspace_id"], "organization_id": provider["organization_id"], "provider": _provider_row(provider, public=True)}


# ---------------------------------------------------------------------------
# Workspace Secret Vault
# ---------------------------------------------------------------------------


def _secret_item(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["reference"] = json_loads(out.pop("reference_json", "{}"), {})
    latest = fetch_one("SELECT version,status,created_at,checksum FROM secret_vault_versions WHERE secret_id=:id ORDER BY version DESC LIMIT 1", {"id": out["id"]})
    out["latest_version"] = latest
    return out


def create_secret(actor_id: str, workspace_id: str, *, name: str, provider: str, value: str = "", reference: dict[str, Any] | None = None) -> dict[str, Any]:
    provider = provider.strip().lower()
    if provider not in {"local_encrypted", "env", "vault_kv2"}:
        raise ValueError("Secret provider non supporté")
    reference = dict(reference or {})
    if provider == "local_encrypted" and not value:
        raise ValueError("Une valeur secrète est requise")
    if provider == "env" and not str(reference.get("variable") or ""):
        raise ValueError("reference.variable est requis")
    if provider == "vault_kv2":
        for key in ["url", "mount", "path", "field"]:
            if not str(reference.get(key) or ""):
                raise ValueError(f"reference.{key} est requis")
        _validate_external_url(str(reference["url"]), resolve_dns=False)
        if not value:
            raise ValueError("Le token Vault est requis et sera chiffré")
    sid = str(uuid.uuid4())
    now = utcnow()
    execute(
        "INSERT INTO secret_vault_items(id,workspace_id,name,provider,reference_json,current_version,created_by,created_at,updated_at) VALUES(:id,:ws,:name,:provider,:ref,0,:user,:now,:now)",
        {"id": sid, "ws": workspace_id, "name": name.strip(), "provider": provider, "ref": json_dumps(reference), "user": actor_id, "now": now},
    )
    rotate_secret(actor_id, workspace_id, sid, value=value)
    return get_secret(workspace_id, sid)


def get_secret(workspace_id: str, secret_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM secret_vault_items WHERE id=:id AND workspace_id=:ws", {"id": secret_id, "ws": workspace_id})
    if not row:
        raise KeyError("Secret introuvable")
    return _secret_item(row)


def list_secrets(workspace_id: str) -> list[dict[str, Any]]:
    return [_secret_item(r) for r in fetch_all("SELECT * FROM secret_vault_items WHERE workspace_id=:ws ORDER BY name", {"ws": workspace_id})]


def rotate_secret(actor_id: str, workspace_id: str, secret_id: str, *, value: str = "") -> dict[str, Any]:
    item = fetch_one("SELECT * FROM secret_vault_items WHERE id=:id AND workspace_id=:ws", {"id": secret_id, "ws": workspace_id})
    if not item:
        raise KeyError("Secret introuvable")
    provider = str(item["provider"])
    if provider in {"local_encrypted", "vault_kv2"} and not value:
        raise ValueError("Nouvelle valeur requise pour la rotation")
    next_version = int(item.get("current_version") or 0) + 1
    previous = int(item.get("current_version") or 0) or None
    raw_for_checksum = value if provider != "env" else json_dumps(json_loads(item.get("reference_json"), {}))
    ciphertext = encrypt_secret(value) if value else ""
    now = utcnow()
    if previous:
        execute("UPDATE secret_vault_versions SET status='retired' WHERE secret_id=:id AND version=:v", {"id": secret_id, "v": previous})
    execute(
        """INSERT INTO secret_vault_versions(id,secret_id,workspace_id,version,ciphertext,checksum,status,created_by,created_at,rotated_from)
           VALUES(:id,:secret,:ws,:version,:cipher,:checksum,'active',:user,:now,:previous)""",
        {"id": str(uuid.uuid4()), "secret": secret_id, "ws": workspace_id, "version": next_version, "cipher": ciphertext,
         "checksum": _hash(raw_for_checksum)[:16], "user": actor_id, "now": now, "previous": previous},
    )
    execute("UPDATE secret_vault_items SET current_version=:v,updated_at=:now WHERE id=:id", {"v": next_version, "now": now, "id": secret_id})
    return get_secret(workspace_id, secret_id)


def resolve_secret(workspace_id: str, secret_id: str) -> str:
    item = fetch_one("SELECT * FROM secret_vault_items WHERE id=:id AND workspace_id=:ws", {"id": secret_id, "ws": workspace_id})
    if not item:
        raise KeyError("Secret introuvable")
    version = fetch_one("SELECT * FROM secret_vault_versions WHERE secret_id=:id AND version=:v", {"id": secret_id, "v": item["current_version"]})
    if not version:
        raise RuntimeError("Version active du secret introuvable")
    provider = str(item["provider"])
    reference = json_loads(item.get("reference_json"), {})
    if provider == "local_encrypted":
        return decrypt_secret(version.get("ciphertext"))
    if provider == "env":
        var = str(reference.get("variable") or "")
        value = os.environ.get(var)
        if value is None:
            raise RuntimeError(f"Variable d'environnement absente: {var}")
        return value
    if provider == "vault_kv2":
        base = str(reference["url"]).rstrip("/")
        _validate_external_url(base, resolve_dns=True)
        mount = str(reference["mount"]).strip("/")
        path = str(reference["path"]).strip("/")
        field = str(reference["field"])
        token = decrypt_secret(version.get("ciphertext"))
        with httpx.Client(timeout=8.0, follow_redirects=False) as client:
            res = client.get(f"{base}/v1/{mount}/data/{path}", headers={"X-Vault-Token": token, "Accept": "application/json", "User-Agent": "DataVision-Secrets/2.12"})
            res.raise_for_status()
            payload = res.json()
        data = ((payload.get("data") or {}).get("data") or {})
        if field not in data:
            raise RuntimeError("Champ Vault introuvable")
        return str(data[field])
    raise RuntimeError("Secret provider non supporté")


def test_secret(workspace_id: str, secret_id: str) -> dict[str, Any]:
    value = resolve_secret(workspace_id, secret_id)
    return {"ok": True, "resolved": True, "length": len(value), "checksum": _hash(value)[:16]}
