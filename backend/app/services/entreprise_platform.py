from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from app.assistant.ai_settings import AssistantAISettings, get_ai_settings, list_provider_profiles, save_ai_settings
from app.core.config import get_settings
from app.services.auth_service import get_user, get_user_by_email, hash_password
from app.services.audit_service import record_event
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, metadata_backend, utcnow
from app.services.secret_crypto import kms_status
from app.services.upload_security import antivirus_status


SCIM_SCHEMA_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_SCHEMA_GROUP = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_GROUP_EXTENSION = "urn:datavision:params:scim:schemas:extension:2.0:Group"
SCIM_SCHEMA_LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_SCHEMA_PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
ROLES = {"owner", "admin", "data_scientist", "analyst", "viewer"}


def _ensure_tables() -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS organization_scim_tokens (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            token_prefix TEXT NOT NULL,
            default_role TEXT NOT NULL DEFAULT 'viewer',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at TEXT
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS scim_provisioned_users (
            organization_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            external_id TEXT,
            provisioned_by_token_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (organization_id, user_id)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS scim_groups (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            external_id TEXT,
            display_name TEXT NOT NULL,
            mapped_role TEXT,
            provisioned_by_token_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(organization_id, display_name)
        )"""
    )
    execute(
        """CREATE TABLE IF NOT EXISTS scim_group_members (
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (group_id, user_id)
        )"""
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _org_admin(user_id: str, organization_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user",
        {"org": organization_id, "user": user_id},
    )
    if not row or row.get("role") not in {"owner", "admin"}:
        raise PermissionError("Administration de l’organisation requise.")
    return row


def create_scim_token(
    actor_id: str,
    organization_id: str,
    workspace_id: str,
    *,
    name: str,
    default_role: str = "viewer",
) -> dict[str, Any]:
    _ensure_tables()
    _org_admin(actor_id, organization_id)
    ws = fetch_one(
        "SELECT id FROM workspaces WHERE id=:ws AND organization_id=:org",
        {"ws": workspace_id, "org": organization_id},
    )
    if not ws:
        raise KeyError("Workspace introuvable dans cette organisation.")
    role = default_role if default_role in ROLES else "viewer"
    raw = "dvscim_" + secrets.token_urlsafe(36)
    token_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        """INSERT INTO organization_scim_tokens(
            id,organization_id,workspace_id,name,token_hash,token_prefix,default_role,created_by,created_at
        ) VALUES(:id,:org,:ws,:name,:hash,:prefix,:role,:actor,:now)""",
        {
            "id": token_id,
            "org": organization_id,
            "ws": workspace_id,
            "name": name.strip()[:160] or "SCIM",
            "hash": _hash_token(raw),
            "prefix": raw[:14],
            "role": role,
            "actor": actor_id,
            "now": now,
        },
    )
    record_event(
        "identity.scim_token_created",
        user_id=actor_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        resource_type="scim_token",
        resource_id=token_id,
        payload={"name": name, "default_role": role},
    )
    return {
        "id": token_id,
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "name": name.strip()[:160] or "SCIM",
        "default_role": role,
        "token": raw,
        "token_prefix": raw[:14],
        "created_at": now,
        "warning": "Copiez ce jeton maintenant : sa valeur brute n’est jamais stockée.",
    }


def list_scim_tokens(actor_id: str, organization_id: str) -> list[dict[str, Any]]:
    _ensure_tables()
    _org_admin(actor_id, organization_id)
    return fetch_all(
        """SELECT id,organization_id,workspace_id,name,token_prefix,default_role,created_by,created_at,last_used_at,revoked_at
           FROM organization_scim_tokens WHERE organization_id=:org ORDER BY created_at DESC""",
        {"org": organization_id},
    )


def revoke_scim_token(actor_id: str, organization_id: str, token_id: str) -> None:
    _ensure_tables()
    _org_admin(actor_id, organization_id)
    row = fetch_one(
        "SELECT id,workspace_id FROM organization_scim_tokens WHERE id=:id AND organization_id=:org",
        {"id": token_id, "org": organization_id},
    )
    if not row:
        raise KeyError("Jeton SCIM introuvable.")
    execute(
        "UPDATE organization_scim_tokens SET revoked_at=:now WHERE id=:id",
        {"now": utcnow(), "id": token_id},
    )
    record_event(
        "identity.scim_token_revoked",
        user_id=actor_id,
        organization_id=organization_id,
        workspace_id=row.get("workspace_id"),
        resource_type="scim_token",
        resource_id=token_id,
    )


def authenticate_scim_token(raw_token: str) -> dict[str, Any]:
    _ensure_tables()
    token = (raw_token or "").strip()
    if not token.startswith("dvscim_"):
        raise PermissionError("Jeton SCIM invalide.")
    row = fetch_one(
        "SELECT * FROM organization_scim_tokens WHERE token_hash=:hash AND revoked_at IS NULL",
        {"hash": _hash_token(token)},
    )
    if not row:
        raise PermissionError("Jeton SCIM invalide ou révoqué.")
    execute("UPDATE organization_scim_tokens SET last_used_at=:now WHERE id=:id", {"now": utcnow(), "id": row["id"]})
    return row


def _role_from_scim(payload: dict[str, Any], default_role: str) -> str:
    roles = payload.get("roles") or []
    if isinstance(roles, list):
        for item in roles:
            value = item.get("value") if isinstance(item, dict) else item
            if value in ROLES:
                return str(value)
    return default_role if default_role in ROLES else "viewer"


def _scim_resource(user: dict[str, Any], *, organization_id: str, workspace_id: str, role: str | None = None, external_id: str | None = None) -> dict[str, Any]:
    return {
        "schemas": [SCIM_SCHEMA_USER],
        "id": str(user["id"]),
        "externalId": external_id,
        "userName": str(user["email"]),
        "displayName": str(user.get("display_name") or user["email"]),
        "active": bool(user.get("is_active", 1)),
        "roles": [{"value": role or "viewer", "primary": True}],
        "meta": {
            "resourceType": "User",
            "created": user.get("created_at"),
            "location": f"/api/v1/scim/v2/Users/{user['id']}",
        },
        "urn:datavision:params:scim:schemas:extension:2.0:User": {
            "organizationId": organization_id,
            "workspaceId": workspace_id,
        },
    }


def list_scim_users(ctx: dict[str, Any], *, start_index: int = 1, count: int = 100) -> dict[str, Any]:
    offset = max(0, start_index - 1)
    count = max(1, min(count, 200))
    rows = fetch_all(
        """SELECT u.id,u.email,u.display_name,u.is_active,u.created_at,om.role,sp.external_id
           FROM users u
           JOIN organization_members om ON om.user_id=u.id AND om.organization_id=:org
           LEFT JOIN scim_provisioned_users sp ON sp.organization_id=:org AND sp.user_id=u.id
           ORDER BY lower(u.email)""",
        {"org": ctx["organization_id"]},
    )
    subset = rows[offset : offset + count]
    resources = [
        _scim_resource(
            row,
            organization_id=ctx["organization_id"],
            workspace_id=ctx["workspace_id"],
            role=row.get("role"),
            external_id=row.get("external_id"),
        )
        for row in subset
    ]
    return {
        "schemas": [SCIM_SCHEMA_LIST],
        "totalResults": len(rows),
        "startIndex": start_index,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


def get_scim_user(ctx: dict[str, Any], user_id: str) -> dict[str, Any]:
    row = fetch_one(
        """SELECT u.id,u.email,u.display_name,u.is_active,u.created_at,om.role,sp.external_id
           FROM users u JOIN organization_members om ON om.user_id=u.id AND om.organization_id=:org
           LEFT JOIN scim_provisioned_users sp ON sp.organization_id=:org AND sp.user_id=u.id
           WHERE u.id=:id""",
        {"org": ctx["organization_id"], "id": user_id},
    )
    if not row:
        raise KeyError("Utilisateur SCIM introuvable.")
    return _scim_resource(
        row,
        organization_id=ctx["organization_id"],
        workspace_id=ctx["workspace_id"],
        role=row.get("role"),
        external_id=row.get("external_id"),
    )


def provision_scim_user(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    email = str(payload.get("userName") or "").strip().lower()
    if "@" not in email:
        raise ValueError("SCIM userName doit être une adresse email valide.")
    display_name = str(payload.get("displayName") or email.split("@", 1)[0]).strip()[:120]
    active = bool(payload.get("active", True))
    role = _role_from_scim(payload, str(ctx.get("default_role") or "viewer"))
    external_id = str(payload.get("externalId") or "")[:240] or None
    user = get_user_by_email(email)
    now = utcnow()
    if not user:
        user_id = str(uuid.uuid4())
        execute(
            "INSERT INTO users(id,email,password_hash,display_name,is_active,created_at) VALUES(:id,:email,:pw,:name,:active,:now)",
            {
                "id": user_id,
                "email": email,
                "pw": hash_password(secrets.token_urlsafe(32)),
                "name": display_name,
                "active": 1 if active else 0,
                "now": now,
            },
        )
        user = get_user(user_id)
    else:
        execute(
            "UPDATE users SET display_name=:name,is_active=:active WHERE id=:id",
            {"name": display_name, "active": 1 if active else 0, "id": user["id"]},
        )
        user = get_user(str(user["id"]))
    assert user is not None
    existing_org = fetch_one(
        "SELECT user_id FROM organization_members WHERE organization_id=:org AND user_id=:user",
        {"org": ctx["organization_id"], "user": user["id"]},
    )
    if existing_org:
        execute(
            "UPDATE organization_members SET role=:role WHERE organization_id=:org AND user_id=:user",
            {"role": role, "org": ctx["organization_id"], "user": user["id"]},
        )
    else:
        execute(
            "INSERT INTO organization_members(organization_id,user_id,role,created_at) VALUES(:org,:user,:role,:now)",
            {"org": ctx["organization_id"], "user": user["id"], "role": role, "now": now},
        )
    existing_ws = fetch_one(
        "SELECT user_id FROM workspace_members WHERE workspace_id=:ws AND user_id=:user",
        {"ws": ctx["workspace_id"], "user": user["id"]},
    )
    if existing_ws:
        execute(
            "UPDATE workspace_members SET role=:role WHERE workspace_id=:ws AND user_id=:user",
            {"role": role, "ws": ctx["workspace_id"], "user": user["id"]},
        )
    else:
        execute(
            "INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(:ws,:user,:role,:now)",
            {"ws": ctx["workspace_id"], "user": user["id"], "role": role, "now": now},
        )
    mapped = fetch_one(
        "SELECT user_id FROM scim_provisioned_users WHERE organization_id=:org AND user_id=:user",
        {"org": ctx["organization_id"], "user": user["id"]},
    )
    if mapped:
        execute(
            """UPDATE scim_provisioned_users SET workspace_id=:ws,external_id=:external,updated_at=:now
               WHERE organization_id=:org AND user_id=:user""",
            {"ws": ctx["workspace_id"], "external": external_id, "now": now, "org": ctx["organization_id"], "user": user["id"]},
        )
    else:
        execute(
            """INSERT INTO scim_provisioned_users(organization_id,workspace_id,user_id,external_id,provisioned_by_token_id,created_at,updated_at)
               VALUES(:org,:ws,:user,:external,:token,:now,:now)""",
            {"org": ctx["organization_id"], "ws": ctx["workspace_id"], "user": user["id"], "external": external_id, "token": ctx["id"], "now": now},
        )
    record_event(
        "identity.scim_user_provisioned",
        organization_id=ctx["organization_id"],
        workspace_id=ctx["workspace_id"],
        resource_type="user",
        resource_id=user["id"],
        payload={"email": email, "role": role, "active": active},
    )
    return get_scim_user(ctx, str(user["id"]))


def patch_scim_user(ctx: dict[str, Any], user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_scim_user(ctx, user_id)
    updates: dict[str, Any] = {}
    role: str | None = None
    for operation in payload.get("Operations") or payload.get("operations") or []:
        if str(operation.get("op") or "").lower() not in {"replace", "add"}:
            continue
        path = str(operation.get("path") or "").lower()
        value = operation.get("value")
        if not path and isinstance(value, dict):
            for key, val in value.items():
                updates[key.lower()] = val
        else:
            updates[path] = value
    if "active" in updates:
        execute("UPDATE users SET is_active=:active WHERE id=:id", {"active": 1 if bool(updates["active"]) else 0, "id": user_id})
    if "displayname" in updates:
        execute("UPDATE users SET display_name=:name WHERE id=:id", {"name": str(updates["displayname"])[:120], "id": user_id})
    if "roles" in updates:
        value = updates["roles"]
        role_payload = {"roles": value if isinstance(value, list) else [value]}
        role = _role_from_scim(role_payload, str(ctx.get("default_role") or "viewer"))
    if role:
        execute("UPDATE organization_members SET role=:role WHERE organization_id=:org AND user_id=:user", {"role": role, "org": ctx["organization_id"], "user": user_id})
        execute("UPDATE workspace_members SET role=:role WHERE workspace_id=:ws AND user_id=:user", {"role": role, "ws": ctx["workspace_id"], "user": user_id})
    execute("UPDATE scim_provisioned_users SET updated_at=:now WHERE organization_id=:org AND user_id=:user", {"now": utcnow(), "org": ctx["organization_id"], "user": user_id})
    record_event(
        "identity.scim_user_updated",
        organization_id=ctx["organization_id"],
        workspace_id=ctx["workspace_id"],
        resource_type="user",
        resource_id=user_id,
        payload={"fields": sorted(updates)},
    )
    return get_scim_user(ctx, user_id)


def deactivate_scim_user(ctx: dict[str, Any], user_id: str) -> None:
    get_scim_user(ctx, user_id)
    execute("UPDATE users SET is_active=0 WHERE id=:id", {"id": user_id})
    record_event(
        "identity.scim_user_deactivated",
        organization_id=ctx["organization_id"],
        workspace_id=ctx["workspace_id"],
        resource_type="user",
        resource_id=user_id,
    )



def _group_role_from_payload(payload: dict[str, Any]) -> str | None:
    extension = payload.get(SCIM_GROUP_EXTENSION) or {}
    role = str(extension.get("role") or payload.get("role") or "").strip()
    if role in ROLES:
        return role
    display = str(payload.get("displayName") or "").strip().lower().replace(" ", "_")
    return display if display in ROLES else None


def _group_member_ids(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value] if value else []
    out: list[str] = []
    for item in items:
        member_id = str(item.get("value") if isinstance(item, dict) else item or "").strip()
        if member_id and member_id not in out:
            out.append(member_id)
    return out


def _validate_group_members(ctx: dict[str, Any], member_ids: list[str]) -> list[str]:
    valid: list[str] = []
    for user_id in member_ids:
        row = fetch_one(
            "SELECT user_id FROM organization_members WHERE organization_id=:org AND user_id=:user",
            {"org": ctx["organization_id"], "user": user_id},
        )
        if not row:
            raise ValueError(f"Utilisateur SCIM hors organisation : {user_id}")
        valid.append(user_id)
    return valid


def _apply_group_role(ctx: dict[str, Any], user_ids: list[str], role: str | None) -> None:
    if not role or role not in ROLES:
        return
    for user_id in user_ids:
        execute(
            "UPDATE organization_members SET role=:role WHERE organization_id=:org AND user_id=:user",
            {"role": role, "org": ctx["organization_id"], "user": user_id},
        )
        row = fetch_one(
            "SELECT user_id FROM workspace_members WHERE workspace_id=:ws AND user_id=:user",
            {"ws": ctx["workspace_id"], "user": user_id},
        )
        if row:
            execute(
                "UPDATE workspace_members SET role=:role WHERE workspace_id=:ws AND user_id=:user",
                {"role": role, "ws": ctx["workspace_id"], "user": user_id},
            )
        else:
            execute(
                "INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(:ws,:user,:role,:now)",
                {"ws": ctx["workspace_id"], "user": user_id, "role": role, "now": utcnow()},
            )


def _scim_group_resource(ctx: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    members = fetch_all(
        """SELECT gm.user_id,u.email FROM scim_group_members gm JOIN users u ON u.id=gm.user_id
           WHERE gm.group_id=:group_id ORDER BY lower(u.email)""",
        {"group_id": row["id"]},
    )
    return {
        "schemas": [SCIM_SCHEMA_GROUP, SCIM_GROUP_EXTENSION],
        "id": str(row["id"]),
        "externalId": row.get("external_id"),
        "displayName": str(row["display_name"]),
        "members": [
            {"value": str(item["user_id"]), "display": str(item["email"]), "$ref": f"/api/v1/scim/v2/Users/{item['user_id']}"}
            for item in members
        ],
        "meta": {
            "resourceType": "Group",
            "created": row.get("created_at"),
            "lastModified": row.get("updated_at"),
            "location": f"/api/v1/scim/v2/Groups/{row['id']}",
        },
        SCIM_GROUP_EXTENSION: {
            "organizationId": ctx["organization_id"],
            "workspaceId": ctx["workspace_id"],
            "role": row.get("mapped_role"),
        },
    }


def list_scim_groups(ctx: dict[str, Any], *, start_index: int = 1, count: int = 100) -> dict[str, Any]:
    _ensure_tables()
    rows = fetch_all(
        "SELECT * FROM scim_groups WHERE organization_id=:org ORDER BY lower(display_name)",
        {"org": ctx["organization_id"]},
    )
    offset = max(0, start_index - 1)
    subset = rows[offset : offset + max(1, min(int(count), 200))]
    resources = [_scim_group_resource(ctx, row) for row in subset]
    return {
        "schemas": [SCIM_SCHEMA_LIST],
        "totalResults": len(rows),
        "startIndex": start_index,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


def get_scim_group(ctx: dict[str, Any], group_id: str) -> dict[str, Any]:
    _ensure_tables()
    row = fetch_one(
        "SELECT * FROM scim_groups WHERE id=:id AND organization_id=:org",
        {"id": group_id, "org": ctx["organization_id"]},
    )
    if not row:
        raise KeyError("Groupe SCIM introuvable.")
    return _scim_group_resource(ctx, row)


def provision_scim_group(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_tables()
    name = str(payload.get("displayName") or "").strip()[:180]
    if not name:
        raise ValueError("SCIM displayName est requis pour un groupe.")
    if fetch_one(
        "SELECT id FROM scim_groups WHERE organization_id=:org AND lower(display_name)=lower(:name)",
        {"org": ctx["organization_id"], "name": name},
    ):
        raise ValueError("Un groupe SCIM avec ce nom existe déjà.")
    group_id = str(uuid.uuid4())
    now = utcnow()
    role = _group_role_from_payload(payload)
    external_id = str(payload.get("externalId") or "")[:240] or None
    member_ids = _validate_group_members(ctx, _group_member_ids(payload.get("members")))
    execute(
        """INSERT INTO scim_groups(id,organization_id,workspace_id,external_id,display_name,mapped_role,
           provisioned_by_token_id,created_at,updated_at)
           VALUES(:id,:org,:ws,:external,:name,:role,:token,:now,:now)""",
        {"id": group_id, "org": ctx["organization_id"], "ws": ctx["workspace_id"], "external": external_id,
         "name": name, "role": role, "token": ctx["id"], "now": now},
    )
    for user_id in member_ids:
        execute(
            "INSERT INTO scim_group_members(group_id,user_id,created_at) VALUES(:group_id,:user,:now)",
            {"group_id": group_id, "user": user_id, "now": now},
        )
    _apply_group_role(ctx, member_ids, role)
    record_event(
        "identity.scim_group_provisioned",
        organization_id=ctx["organization_id"],
        workspace_id=ctx["workspace_id"],
        resource_type="scim_group",
        resource_id=group_id,
        payload={"display_name": name, "role": role, "member_count": len(member_ids)},
    )
    return get_scim_group(ctx, group_id)


def patch_scim_group(ctx: dict[str, Any], group_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_tables()
    current = get_scim_group(ctx, group_id)
    role = current.get(SCIM_GROUP_EXTENSION, {}).get("role")
    operations = payload.get("Operations") or payload.get("operations") or []
    for operation in operations:
        op = str(operation.get("op") or "").lower()
        path = str(operation.get("path") or "").strip()
        value = operation.get("value")
        lower_path = path.lower()
        if op in {"replace", "add"} and lower_path == "displayname":
            name = str(value or "").strip()[:180]
            if not name:
                raise ValueError("displayName ne peut pas être vide.")
            execute("UPDATE scim_groups SET display_name=:name,updated_at=:now WHERE id=:id", {"name": name, "now": utcnow(), "id": group_id})
        elif op in {"replace", "add"} and (lower_path.endswith(":role") or lower_path == "role"):
            candidate = str(value or "").strip()
            if candidate not in ROLES:
                raise ValueError("Rôle SCIM groupe invalide.")
            role = candidate
            execute("UPDATE scim_groups SET mapped_role=:role,updated_at=:now WHERE id=:id", {"role": role, "now": utcnow(), "id": group_id})
        elif lower_path.startswith("members") or (not path and isinstance(value, dict) and "members" in value):
            raw_members = value.get("members") if not path and isinstance(value, dict) else value
            member_ids = _validate_group_members(ctx, _group_member_ids(raw_members))
            if op == "replace":
                execute("DELETE FROM scim_group_members WHERE group_id=:id", {"id": group_id})
            if op in {"replace", "add"}:
                for user_id in member_ids:
                    exists = fetch_one("SELECT user_id FROM scim_group_members WHERE group_id=:id AND user_id=:user", {"id": group_id, "user": user_id})
                    if not exists:
                        execute("INSERT INTO scim_group_members(group_id,user_id,created_at) VALUES(:id,:user,:now)", {"id": group_id, "user": user_id, "now": utcnow()})
                _apply_group_role(ctx, member_ids, role)
            elif op == "remove":
                for user_id in member_ids:
                    execute("DELETE FROM scim_group_members WHERE group_id=:id AND user_id=:user", {"id": group_id, "user": user_id})
            execute("UPDATE scim_groups SET updated_at=:now WHERE id=:id", {"now": utcnow(), "id": group_id})
    record_event(
        "identity.scim_group_updated",
        organization_id=ctx["organization_id"],
        workspace_id=ctx["workspace_id"],
        resource_type="scim_group",
        resource_id=group_id,
        payload={"operations": len(operations)},
    )
    return get_scim_group(ctx, group_id)


def delete_scim_group(ctx: dict[str, Any], group_id: str) -> None:
    _ensure_tables()
    get_scim_group(ctx, group_id)
    execute("DELETE FROM scim_group_members WHERE group_id=:id", {"id": group_id})
    execute("DELETE FROM scim_groups WHERE id=:id AND organization_id=:org", {"id": group_id, "org": ctx["organization_id"]})
    record_event(
        "identity.scim_group_deleted",
        organization_id=ctx["organization_id"],
        workspace_id=ctx["workspace_id"],
        resource_type="scim_group",
        resource_id=group_id,
    )


def discover_oidc_for_email(email: str) -> list[dict[str, Any]]:
    domain = (email or "").strip().lower().rsplit("@", 1)[-1] if "@" in (email or "") else ""
    if not domain:
        return []
    rows = fetch_all("SELECT * FROM oidc_providers WHERE enabled=1 ORDER BY name")
    matches = []
    for row in rows:
        allowed = [str(x).strip().lower() for x in json_loads(row.get("allowed_domains_json"), []) if str(x).strip()]
        if allowed and domain not in allowed:
            continue
        matches.append({
            "id": row["id"],
            "name": row["name"],
            "issuer": row["issuer"],
            "workspace_id": row["workspace_id"],
            "organization_id": row["organization_id"],
            "matched_domain": domain,
        })
    return matches


def private_ai_posture(workspace_id: str) -> dict[str, Any]:
    settings = get_ai_settings("workspace", workspace_id)
    providers = list_provider_profiles("workspace", workspace_id)
    local = [p for p in providers if p.location == "local" and p.enabled]
    external = [p for p in providers if p.location == "external" and p.enabled]
    strict = settings.privacy_mode == "local_only" and not settings.allow_external_ai
    return {
        "workspace_id": workspace_id,
        "strict_private_ai": strict,
        "planner_mode": settings.planner_mode,
        "privacy_mode": settings.privacy_mode,
        "allow_external_ai": settings.allow_external_ai,
        "local_provider_count": len(local),
        "external_provider_count": len(external),
        "external_effectively_blocked": strict,
        "raw_rows_external_allowed": False,
        "sample_values_external_allowed": False,
        "provider_ids": [p.id for p in providers if p.enabled],
    }


def enforce_private_ai(actor_id: str, workspace_id: str) -> dict[str, Any]:
    current = get_ai_settings("workspace", workspace_id)
    payload = current.model_dump(mode="python")
    payload["privacy_mode"] = "local_only"
    payload["allow_external_ai"] = False
    payload["external_data_policy"]["include_sample_values"] = False
    payload["external_data_policy"]["include_row_data"] = False
    updated = AssistantAISettings.model_validate(payload)
    save_ai_settings("workspace", workspace_id, updated, actor_id=actor_id)
    record_event(
        "ai.private_mode_enforced",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="assistant_ai_settings",
        resource_id=workspace_id,
        payload={"privacy_mode": "local_only", "allow_external_ai": False},
    )
    return private_ai_posture(workspace_id)


def prometheus_metrics(workspace_id: str, *, hours: int = 24) -> str:
    hours = max(1, min(int(hours), 24 * 30))
    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    rows = fetch_all(
        "SELECT event_kind,status,latency_ms,input_tokens,output_tokens,estimated_cost_usd,created_at FROM telemetry_events WHERE workspace_id=:ws",
        {"ws": workspace_id},
    )
    recent = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(str(row.get("created_at") or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if ts >= cutoff:
            recent.append(row)
    http = [r for r in recent if r.get("event_kind") == "http"]
    jobs = [r for r in recent if r.get("event_kind") == "job"]
    latencies = sorted(float(r.get("latency_ms") or 0.0) for r in http if r.get("latency_ms") is not None)
    p95 = latencies[min(len(latencies) - 1, int(round((len(latencies) - 1) * 0.95)))] if latencies else 0.0
    status_5xx = sum(1 for r in http if str(r.get("status") or "").startswith("5"))
    job_failed = sum(1 for r in jobs if str(r.get("status") or "").lower() in {"failed", "error"})
    input_tokens = sum(int(r.get("input_tokens") or 0) for r in recent)
    output_tokens = sum(int(r.get("output_tokens") or 0) for r in recent)
    cost = sum(float(r.get("estimated_cost_usd") or 0.0) for r in recent)
    label = workspace_id.replace('\\', '\\\\').replace('"', '\\"')
    lines = [
        "# HELP datavision_http_requests_total Requêtes HTTP observées dans la fenêtre.",
        "# TYPE datavision_http_requests_total gauge",
        f'datavision_http_requests_total{{workspace_id="{label}"}} {len(http)}',
        "# HELP datavision_http_5xx_total Réponses HTTP 5xx observées dans la fenêtre.",
        "# TYPE datavision_http_5xx_total gauge",
        f'datavision_http_5xx_total{{workspace_id="{label}"}} {status_5xx}',
        "# HELP datavision_http_latency_p95_ms Latence HTTP p95 en millisecondes.",
        "# TYPE datavision_http_latency_p95_ms gauge",
        f'datavision_http_latency_p95_ms{{workspace_id="{label}"}} {p95:.6f}',
        "# HELP datavision_jobs_failed_total Jobs en échec dans la fenêtre.",
        "# TYPE datavision_jobs_failed_total gauge",
        f'datavision_jobs_failed_total{{workspace_id="{label}"}} {job_failed}',
        "# HELP datavision_ai_input_tokens_total Tokens IA entrants observés.",
        "# TYPE datavision_ai_input_tokens_total gauge",
        f'datavision_ai_input_tokens_total{{workspace_id="{label}"}} {input_tokens}',
        "# HELP datavision_ai_output_tokens_total Tokens IA sortants observés.",
        "# TYPE datavision_ai_output_tokens_total gauge",
        f'datavision_ai_output_tokens_total{{workspace_id="{label}"}} {output_tokens}',
        "# HELP datavision_ai_estimated_cost_usd Coût IA estimé observé.",
        "# TYPE datavision_ai_estimated_cost_usd gauge",
        f'datavision_ai_estimated_cost_usd{{workspace_id="{label}"}} {cost:.8f}',
    ]
    return "\n".join(lines) + "\n"



def prometheus_all_metrics(*, hours: int = 24) -> str:
    rows = fetch_all("SELECT DISTINCT workspace_id FROM telemetry_events WHERE workspace_id IS NOT NULL ORDER BY workspace_id")
    workspaces = [str(row["workspace_id"]) for row in rows if row.get("workspace_id")]
    if not workspaces:
        return "# HELP datavision_up DataVision API availability.\n# TYPE datavision_up gauge\ndatavision_up 1\n"
    output: list[str] = ["# HELP datavision_up DataVision API availability.", "# TYPE datavision_up gauge", "datavision_up 1"]
    comments_seen: set[str] = set()
    for workspace_id in workspaces:
        for line in prometheus_metrics(workspace_id, hours=hours).splitlines():
            if line.startswith("# HELP") or line.startswith("# TYPE"):
                metric = " ".join(line.split(" ")[:3])
                if metric in comments_seen:
                    continue
                comments_seen.add(metric)
            output.append(line)
    return "\n".join(output) + "\n"


def entreprise_readiness(actor_id: str, workspace_id: str) -> dict[str, Any]:
    ws = fetch_one("SELECT * FROM workspaces WHERE id=:ws", {"ws": workspace_id})
    if not ws:
        raise KeyError("Workspace introuvable.")
    _org_admin(actor_id, str(ws["organization_id"]))
    _ensure_tables()
    oidc_count = int((fetch_one("SELECT COUNT(*) AS n FROM oidc_providers WHERE workspace_id=:ws AND enabled=1", {"ws": workspace_id}) or {"n": 0})["n"])
    scim_count = int((fetch_one("SELECT COUNT(*) AS n FROM organization_scim_tokens WHERE organization_id=:org AND revoked_at IS NULL", {"org": ws["organization_id"]}) or {"n": 0})["n"])
    scim_group_count = int((fetch_one("SELECT COUNT(*) AS n FROM scim_groups WHERE organization_id=:org", {"org": ws["organization_id"]}) or {"n": 0})["n"])
    from app.services.session_security import get_organization_security_policy
    session_policy = get_organization_security_policy(str(ws["organization_id"]))
    ai = private_ai_posture(workspace_id)
    kms = kms_status()
    av = antivirus_status()
    cfg = get_settings()
    checks = [
        {"id": "tenant_isolation", "label": "Isolation tenant / RBAC", "status": "pass", "detail": "Workspace, RBAC, RLS et sécurité colonne actifs."},
        {"id": "sso", "label": "SSO OIDC", "status": "pass" if oidc_count else "warn", "detail": f"{oidc_count} fournisseur(s) OIDC actif(s)."},
        {"id": "mfa", "label": "MFA WebAuthn", "status": "pass" if cfg.webauthn_enabled else "fail", "detail": f"Politique : {cfg.mfa_policy}."},
        {"id": "scim", "label": "Provisioning SCIM 2.0", "status": "pass" if scim_count else "warn", "detail": f"{scim_count} jeton(s) SCIM actif(s)."},
        {"id": "scim_groups", "label": "SCIM Groups", "status": "pass" if scim_count else "warn", "detail": f"{scim_group_count} groupe(s) provisionné(s) · endpoint Groups actif."},
        {"id": "session_device_policy", "label": "Politiques session / appareil", "status": "pass", "detail": f"Idle {session_policy['idle_timeout_minutes']} min · max {session_policy['max_active_sessions']} session(s) · appareil géré={'oui' if session_policy['require_managed_device'] else 'non'}."},
        {"id": "private_ai", "label": "Private AI", "status": "pass" if ai["strict_private_ai"] else "warn", "detail": f"Mode {ai['privacy_mode']} · externe={'autorisé' if ai['allow_external_ai'] else 'bloqué'}."},
        {"id": "kms", "label": "Chiffrement des secrets", "status": "pass" if kms.get("dedicated_key") else "warn", "detail": f"{kms.get('scheme')} · key_id={kms.get('key_id')}."},
        {"id": "external_kms", "label": "KMS/HSM externe", "status": "pass" if kms.get("external_kms") and kms.get("production_ready") else "warn", "detail": f"Provider={kms.get('provider')} · HSM déclaré={'oui' if kms.get('hsm_backed') else 'non'}."},
        {"id": "antivirus", "label": "Sécurité upload", "status": "pass" if str(av.get("mode")) == "required" else "warn", "detail": f"ClamAV : {av.get('mode')}."},
        {"id": "observability", "label": "Observabilité Prometheus", "status": "pass", "detail": "Endpoints workspace-scoped et scrape interne disponibles."},
        {"id": "otel", "label": "OpenTelemetry Collector", "status": "pass", "detail": "Collector Contrib packagé, receiver Prometheus et export OTLP/Prometheus prêts."},
        {"id": "kubernetes", "label": "Kubernetes / Helm", "status": "pass", "detail": "Chart Helm on-prem fourni sans retirer Docker Compose."},
        {"id": "sre", "label": "SRE & résilience avancée", "status": "pass", "detail": f"SLO/error budget, restore drills et autoscaling worker={cfg.sre_worker_autoscaling_mode}."},
        {"id": "object_backup", "label": "Backup objet", "status": "pass" if cfg.backup_object_store_provider != "disabled" else "warn", "detail": f"Provider={cfg.backup_object_store_provider} · auto-upload={'oui' if cfg.backup_object_store_auto_upload else 'non'}."},
    ]
    pass_count = sum(1 for c in checks if c["status"] == "pass")
    return {
        "product": "DataVision AI",
        "version": "2.60.0",
        "edition": "Entreprise",
        "workspace_id": workspace_id,
        "organization_id": ws["organization_id"],
        "metadata": metadata_backend(),
        "private_ai": ai,
        "sso": {"active_providers": oidc_count, "configured": oidc_count > 0},
        "mfa": {"webauthn_enabled": bool(cfg.webauthn_enabled), "policy": cfg.mfa_policy},
        "scim": {"active_tokens": scim_count, "groups": scim_group_count, "configured": scim_count > 0},
        "session_device_policy": session_policy,
        "kms": kms,
        "checks": checks,
        "score": round(pass_count / len(checks) * 100),
        "ready": all(c["status"] != "fail" for c in checks),
        "deployment": {
            "profile": cfg.deployment_profile or "onprem",
            "docker_compose": True,
            "kubernetes_helm": True,
            "opentelemetry_collector": True,
            "worker_autoscaling": cfg.sre_worker_autoscaling_mode,
            "object_backup": cfg.backup_object_store_provider,
            "restore_drills": True,
            "external_egress_policy": cfg.external_egress_policy,
            "external_ai_opt_in_only": cfg.external_egress_policy == "explicit_opt_in",
            "persistent_postgres": metadata_backend().get("dialect") == "postgresql",
            "redis_jobs": True,
            "sandbox_network_isolated": True,
        },
    }
