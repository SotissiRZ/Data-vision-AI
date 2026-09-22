from __future__ import annotations

import uuid
from typing import Any

from app.services.auth_service import ROLES, has_permission, workspace_role, hash_password
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, slugify, utcnow
from app.services.product_plans import assert_organization_workspace_quota, assert_workspace_resource_quota


def create_workspace(user_id: str, organization_id: str, name: str) -> dict[str, Any]:
    org_member = fetch_one("SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org": organization_id, "user": user_id})
    if not org_member or org_member["role"] not in {"owner", "admin"}:
        raise PermissionError("Permission insuffisante pour créer un workspace.")
    assert_organization_workspace_quota(organization_id)
    ws_id = str(uuid.uuid4())
    now = utcnow()
    base = slugify(name)
    slug = base
    i = 2
    while fetch_one("SELECT id FROM workspaces WHERE organization_id=:org AND slug=:slug", {"org": organization_id, "slug": slug}):
        slug = f"{base}-{i}"; i += 1
    execute("INSERT INTO workspaces(id,organization_id,name,slug,created_by,created_at) VALUES(:id,:org,:name,:slug,:user,:created)", {"id": ws_id, "org": organization_id, "name": name.strip() or "Workspace", "slug": slug, "user": user_id, "created": now})
    execute("INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(:ws,:user,:role,:created)", {"ws": ws_id, "user": user_id, "role": "owner" if org_member["role"] == "owner" else "admin", "created": now})
    return get_workspace(user_id, ws_id)


def get_workspace(user_id: str, workspace_id: str) -> dict[str, Any]:
    role = workspace_role(user_id, workspace_id)
    if not role:
        raise PermissionError("Accès au workspace refusé.")
    row = fetch_one("SELECT * FROM workspaces WHERE id=:id", {"id": workspace_id})
    if not row:
        raise KeyError("Workspace introuvable")
    row["role"] = role
    row["members_count"] = int((fetch_one("SELECT COUNT(*) AS n FROM workspace_members WHERE workspace_id=:ws", {"ws": workspace_id}) or {"n": 0})["n"])
    row["datasets_count"] = int((fetch_one("SELECT COUNT(*) AS n FROM workspace_datasets WHERE workspace_id=:ws", {"ws": workspace_id}) or {"n": 0})["n"])
    return row


def list_members(user_id: str, workspace_id: str) -> list[dict[str, Any]]:
    if not workspace_role(user_id, workspace_id):
        raise PermissionError("Accès au workspace refusé.")
    return fetch_all("""
        SELECT u.id,u.email,u.display_name,wm.role,wm.created_at
        FROM workspace_members wm JOIN users u ON u.id=wm.user_id
        WHERE wm.workspace_id=:ws ORDER BY u.display_name
    """, {"ws": workspace_id})


def upsert_member(actor_id: str, workspace_id: str, email: str, role: str, *, display_name: str | None = None, password: str | None = None) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError("Rôle invalide")
    if not has_permission(actor_id, workspace_id, "members:manage"):
        raise PermissionError("Permission insuffisante pour gérer les membres.")
    user = fetch_one("SELECT id,email,display_name FROM users WHERE lower(email)=lower(:email)", {"email": email.strip()})
    now = utcnow()
    if not user:
        if not password:
            raise KeyError("Utilisateur introuvable. Fournissez un mot de passe initial pour le provisionner.")
        uid = str(uuid.uuid4())
        name = (display_name or email.split("@")[0]).strip()
        execute("INSERT INTO users(id,email,password_hash,display_name,is_active,created_at) VALUES(:id,:email,:pw,:name,1,:created)", {"id":uid,"email":email.strip().lower(),"pw":hash_password(password),"name":name,"created":now})
        user = {"id": uid, "email": email.strip().lower(), "display_name": name}
        ws = fetch_one("SELECT organization_id FROM workspaces WHERE id=:ws", {"ws": workspace_id})
        if ws:
            existing_org = fetch_one("SELECT user_id FROM organization_members WHERE organization_id=:org AND user_id=:user", {"org":ws["organization_id"],"user":uid})
            if not existing_org:
                execute("INSERT INTO organization_members(organization_id,user_id,role,created_at) VALUES(:org,:user,:role,:created)", {"org":ws["organization_id"],"user":uid,"role":role,"created":now})
    existing = fetch_one("SELECT user_id FROM workspace_members WHERE workspace_id=:ws AND user_id=:user", {"ws": workspace_id, "user": user["id"]})
    if not existing:
        assert_workspace_resource_quota(workspace_id, "members")
    if existing:
        execute("UPDATE workspace_members SET role=:role WHERE workspace_id=:ws AND user_id=:user", {"role": role, "ws": workspace_id, "user": user["id"]})
    else:
        execute("INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(:ws,:user,:role,:created)", {"ws": workspace_id, "user": user["id"], "role": role, "created": now})
    return {**user, "role": role}


def bind_dataset(actor_id: str, workspace_id: str, dataset_id: str) -> dict[str, Any]:
    if not has_permission(actor_id, workspace_id, "dataset:write"):
        raise PermissionError("Permission insuffisante pour lier un dataset.")
    existing = fetch_one("SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws AND dataset_id=:ds", {"ws": workspace_id, "ds": dataset_id})
    if not existing:
        assert_workspace_resource_quota(workspace_id, "datasets")
        execute("INSERT INTO workspace_datasets(workspace_id,dataset_id,bound_by,created_at) VALUES(:ws,:ds,:user,:created)", {"ws": workspace_id, "ds": dataset_id, "user": actor_id, "created": utcnow()})
    return {"workspace_id": workspace_id, "dataset_id": dataset_id, "bound": True}


def list_workspace_datasets(user_id: str, workspace_id: str) -> list[dict[str, Any]]:
    if not has_permission(user_id, workspace_id, "dataset:read"):
        raise PermissionError("Permission insuffisante pour lire les datasets.")
    return fetch_all("SELECT dataset_id,bound_by,created_at FROM workspace_datasets WHERE workspace_id=:ws ORDER BY created_at DESC", {"ws": workspace_id})


def save_access_policy(actor_id: str, workspace_id: str, dataset_id: str, name: str, allowed_columns: list[str], row_filters: list[dict[str, Any]], applies_to_role: str | None = None, policy_id: str | None = None) -> dict[str, Any]:
    if not has_permission(actor_id, workspace_id, "policies:manage"):
        raise PermissionError("Permission insuffisante pour gérer les politiques.")
    if applies_to_role and applies_to_role not in ROLES:
        raise ValueError("Rôle invalide")
    now = utcnow(); pid = policy_id or str(uuid.uuid4())
    if fetch_one("SELECT id FROM access_policies WHERE id=:id", {"id": pid}):
        execute("UPDATE access_policies SET name=:name,allowed_columns_json=:cols,row_filters_json=:filters,applies_to_role=:role,updated_at=:updated WHERE id=:id AND workspace_id=:ws", {"name": name, "cols": json_dumps(allowed_columns), "filters": json_dumps(row_filters), "role": applies_to_role, "updated": now, "id": pid, "ws": workspace_id})
    else:
        execute("INSERT INTO access_policies(id,workspace_id,dataset_id,name,allowed_columns_json,row_filters_json,applies_to_role,created_by,created_at,updated_at) VALUES(:id,:ws,:ds,:name,:cols,:filters,:role,:user,:created,:updated)", {"id": pid, "ws": workspace_id, "ds": dataset_id, "name": name, "cols": json_dumps(allowed_columns), "filters": json_dumps(row_filters), "role": applies_to_role, "user": actor_id, "created": now, "updated": now})
    return get_policy(actor_id, workspace_id, pid)


def get_policy(user_id: str, workspace_id: str, policy_id: str) -> dict[str, Any]:
    if not workspace_role(user_id, workspace_id):
        raise PermissionError("Accès au workspace refusé.")
    row = fetch_one("SELECT * FROM access_policies WHERE id=:id AND workspace_id=:ws", {"id": policy_id, "ws": workspace_id})
    if not row: raise KeyError("Politique introuvable")
    row["allowed_columns"] = json_loads(row.pop("allowed_columns_json"), [])
    row["row_filters"] = json_loads(row.pop("row_filters_json"), [])
    return row


def list_policies(user_id: str, workspace_id: str) -> list[dict[str, Any]]:
    if not workspace_role(user_id, workspace_id):
        raise PermissionError("Accès au workspace refusé.")
    rows = fetch_all("SELECT * FROM access_policies WHERE workspace_id=:ws ORDER BY updated_at DESC", {"ws": workspace_id})
    for row in rows:
        row["allowed_columns"] = json_loads(row.pop("allowed_columns_json"), [])
        row["row_filters"] = json_loads(row.pop("row_filters_json"), [])
    return rows


def policies_for_access(user_id: str, workspace_id: str, dataset_id: str, role_override: str | None = None) -> list[dict[str, Any]]:
    role = workspace_role(user_id, workspace_id)
    if not role:
        raise PermissionError("Accès au workspace refusé.")
    effective_role = role_override or role
    rows = fetch_all("SELECT * FROM access_policies WHERE workspace_id=:ws AND dataset_id=:ds AND (applies_to_role IS NULL OR applies_to_role=:role) ORDER BY updated_at DESC", {"ws": workspace_id, "ds": dataset_id, "role": effective_role})
    for row in rows:
        row["allowed_columns"] = json_loads(row.pop("allowed_columns_json"), [])
        row["row_filters"] = json_loads(row.pop("row_filters_json"), [])
    return rows


def apply_access_policies(df, policies: list[dict[str, Any]]):
    import pandas as pd
    work = df.copy()
    applied: list[dict[str, Any]] = []

    # Security invariant: row-level rules are evaluated BEFORE column projection.
    # Otherwise a filter column omitted from allowed_columns could disappear first and the
    # row restriction would silently be skipped.
    for policy in policies:
        for f in policy.get("row_filters") or []:
            col = f.get("column"); op = f.get("operator", "eq"); value = f.get("value"); value2 = f.get("value2")
            if not col or col not in work.columns:
                # A malformed policy must never broaden access. Fail closed instead.
                raise ValueError(f"Politique RLS invalide: colonne introuvable {col!r}")
            s = work[col]
            if op == "eq": mask = s == value
            elif op == "neq": mask = s != value
            elif op == "gt": mask = pd.to_numeric(s, errors="coerce") > float(value)
            elif op == "gte": mask = pd.to_numeric(s, errors="coerce") >= float(value)
            elif op == "lt": mask = pd.to_numeric(s, errors="coerce") < float(value)
            elif op == "lte": mask = pd.to_numeric(s, errors="coerce") <= float(value)
            elif op == "contains": mask = s.astype(str).str.contains(str(value), case=False, na=False)
            elif op == "in":
                vals = value if isinstance(value, list) else [x.strip() for x in str(value).split(",")]
                mask = s.isin(vals)
            elif op == "between":
                num = pd.to_numeric(s, errors="coerce"); mask = num.between(float(value), float(value2), inclusive="both")
            elif op == "is_null": mask = s.isna()
            elif op == "not_null": mask = s.notna()
            else:
                raise ValueError(f"Politique RLS invalide: opérateur non supporté {op!r}")
            work = work.loc[mask].copy()
            applied.append({"type":"row_security","column":col,"operator":op,"value":value,"value2":value2})

    column_sets = [set(p.get("allowed_columns") or []) for p in policies if p.get("allowed_columns")]
    if column_sets:
        allowed = set.intersection(*column_sets) if len(column_sets) > 1 else column_sets[0]
        keep = [c for c in work.columns if str(c) in allowed]
        work = work[keep]
        applied.append({"type":"column_security","columns":keep})
    return work, applied
