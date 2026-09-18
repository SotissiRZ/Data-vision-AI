from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from app.services.auth_service import decode_token, get_user, has_permission, workspace_role, validate_session_payload
from app.services.metadata_store import fetch_all, fetch_one, execute, utcnow


@dataclass(frozen=True)
class DataAccessContext:
    user_id: str
    email: str
    workspace_id: str
    role: str
    organization_id: str | None = None


_ACCESS_CONTEXT: ContextVar[DataAccessContext | None] = ContextVar("datavision_access_context", default=None)


def current_access_context() -> DataAccessContext | None:
    return _ACCESS_CONTEXT.get()


def set_access_context(ctx: DataAccessContext | None) -> Token:
    return _ACCESS_CONTEXT.set(ctx)


def reset_access_context(token: Token) -> None:
    _ACCESS_CONTEXT.reset(token)


def build_access_context(authorization: str | None, workspace_id: str | None) -> DataAccessContext | None:
    """Build an Enterprise data-access context.

    Local mode intentionally remains supported: when neither header is present, no governed
    context is created. If either header is provided, both become mandatory so an authenticated
    request can never silently fall back to unrestricted local access.
    """
    if not authorization and not workspace_id:
        return None
    if not authorization or not authorization.lower().startswith("bearer "):
        raise PermissionError("Authentification Bearer requise pour l'accès gouverné.")
    if not workspace_id:
        raise PermissionError("X-Workspace-ID est requis pour l'accès gouverné.")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    validate_session_payload(payload)
    user = get_user(payload.get("sub", ""))
    if not user or not user.get("is_active", True):
        raise PermissionError("Utilisateur introuvable ou désactivé.")
    role = workspace_role(user["id"], workspace_id)
    if not role:
        raise PermissionError("Accès au workspace refusé.")
    ws = fetch_one("SELECT organization_id FROM workspaces WHERE id=:id", {"id": workspace_id}) or {}
    return DataAccessContext(
        user_id=user["id"],
        email=user.get("email", payload.get("email", "")),
        workspace_id=workspace_id,
        role=role,
        organization_id=ws.get("organization_id"),
    )


def require_workspace_permission(permission: str, ctx: DataAccessContext | None = None) -> DataAccessContext:
    ctx = ctx or current_access_context()
    if not ctx:
        raise PermissionError("Contexte Enterprise absent.")
    if not has_permission(ctx.user_id, ctx.workspace_id, permission):
        raise PermissionError(f"Permission insuffisante: {permission}.")
    return ctx


def _lineage_ids(dataset_id: str) -> list[str]:
    """Return current dataset + ancestors without importing storage at module import time."""
    from app.services.storage import get_meta

    ids: list[str] = []
    seen: set[str] = set()
    current = dataset_id
    while current and current not in seen:
        seen.add(current)
        ids.append(current)
        try:
            meta = get_meta(current)
        except FileNotFoundError:
            break
        current = meta.get("parent_id")
    return ids


def _root_id(dataset_id: str) -> str:
    from app.services.storage import get_meta
    meta = get_meta(dataset_id)
    return str(meta.get("root_id") or meta.get("id") or dataset_id)


def dataset_is_bound(ctx: DataAccessContext, dataset_id: str) -> bool:
    """A workspace binding on any version in the same lineage grants access to that lineage.

    This keeps older v2.1 workspaces compatible when only one version had been explicitly bound,
    while still preventing cross-workspace access to unrelated local datasets.
    """
    lineage = _lineage_ids(dataset_id)
    root = _root_id(dataset_id)
    rows = fetch_all("SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws", {"ws": ctx.workspace_id})
    bound = {str(r["dataset_id"]) for r in rows}
    if bound.intersection(lineage):
        return True
    # A bound descendant or sibling from the same root also counts.
    from app.services.storage import get_meta
    for ds_id in bound:
        try:
            meta = get_meta(ds_id)
        except Exception:
            continue
        if str(meta.get("root_id") or meta.get("id")) == root:
            return True
    return False


def authorize_dataset(dataset_id: str, permission: str = "dataset:read", ctx: DataAccessContext | None = None) -> DataAccessContext | None:
    """Authorize a dataset when governed context is active; local mode is left untouched."""
    ctx = ctx or current_access_context()
    if not ctx:
        return None
    require_workspace_permission(permission, ctx)
    if not dataset_is_bound(ctx, dataset_id):
        raise PermissionError("Ce dataset n'est pas lié au workspace actif.")
    return ctx


def inherited_policies(dataset_id: str, ctx: DataAccessContext | None = None) -> list[dict[str, Any]]:
    """Policies inherit down dataset lineage and remain additive/restrictive.

    A policy saved on v1 therefore continues to protect v2/v3. Policies on a more recent version
    are combined with inherited ones; column rules intersect and row filters are ANDed by the
    existing policy engine.
    """
    from app.services.workspace_service import policies_for_access

    ctx = ctx or current_access_context()
    if not ctx:
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ds_id in _lineage_ids(dataset_id):
        try:
            rows = policies_for_access(ctx.user_id, ctx.workspace_id, ds_id)
        except PermissionError:
            raise
        for row in rows:
            pid = str(row.get("id") or f"{ds_id}:{row.get('name')}")
            if pid not in seen:
                seen.add(pid)
                result.append(row)
    return result


def govern_dataframe(dataset_id: str, df, ctx: DataAccessContext | None = None):
    """Apply effective row + column policies to a dataframe in governed mode."""
    from app.services.workspace_service import apply_access_policies

    ctx = authorize_dataset(dataset_id, "dataset:read", ctx)
    if not ctx:
        return df, []
    policies = inherited_policies(dataset_id, ctx)

    # A derived immutable version may already be a materialization of RLS-filtered rows.
    # Requiring an old filter column that was intentionally hidden/dropped would make the
    # secure derivative unreadable. We therefore skip ONLY the row rules whose exact policy
    # version (id + updated_at) is recorded in the child metadata. Current column security is
    # still applied, and any policy changed after materialization is evaluated again.
    try:
        from app.services.storage import get_meta
        materialization = get_meta(dataset_id).get("governance_materialization") or {}
        snapshots = {
            (str(x.get("id")), str(x.get("updated_at")))
            for x in materialization.get("policy_versions", []) if x.get("id")
        }
        if materialization.get("row_security_materialized") and snapshots:
            adjusted = []
            for policy in policies:
                copy = dict(policy)
                key = (str(policy.get("id")), str(policy.get("updated_at")))
                if key in snapshots:
                    copy["row_filters"] = []
                adjusted.append(copy)
            policies = adjusted
    except Exception:
        pass

    governed, applied = apply_access_policies(df, policies)
    return governed, applied


def bind_derived_dataset(parent_id: str, dataset_id: str) -> None:
    """Automatically keep immutable derived versions inside the active workspace lineage."""
    ctx = current_access_context()
    if not ctx:
        return
    authorize_dataset(parent_id, "dataset:write", ctx)
    existing = fetch_one(
        "SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws AND dataset_id=:ds",
        {"ws": ctx.workspace_id, "ds": dataset_id},
    )
    if not existing:
        execute(
            "INSERT INTO workspace_datasets(workspace_id,dataset_id,bound_by,created_at) VALUES(:ws,:ds,:user,:created)",
            {"ws": ctx.workspace_id, "ds": dataset_id, "user": ctx.user_id, "created": utcnow()},
        )


def governed_catalog_ids(ctx: DataAccessContext | None = None) -> set[str] | None:
    """Return dataset ids visible through the active workspace, including lineage siblings."""
    ctx = ctx or current_access_context()
    if not ctx:
        return None
    require_workspace_permission("dataset:read", ctx)
    rows = fetch_all("SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws", {"ws": ctx.workspace_id})
    bound = {str(r["dataset_id"]) for r in rows}
    roots: set[str] = set()
    from app.services.storage import get_meta
    for ds_id in bound:
        try:
            meta = get_meta(ds_id)
            roots.add(str(meta.get("root_id") or meta.get("id")))
        except Exception:
            continue
    # The caller has metadata at hand and can include all versions matching these roots.
    return roots


def access_summary(dataset_id: str | None = None) -> dict[str, Any]:
    ctx = current_access_context()
    if not ctx:
        return {"mode": "local", "governed": False}
    data: dict[str, Any] = {
        "mode": "enterprise",
        "governed": True,
        "workspace_id": ctx.workspace_id,
        "organization_id": ctx.organization_id,
        "role": ctx.role,
        "user_id": ctx.user_id,
    }
    if dataset_id:
        policies = inherited_policies(dataset_id, ctx)
        data["dataset_id"] = dataset_id
        data["policy_count"] = len(policies)
        data["policy_ids"] = [p.get("id") for p in policies]
    return data


def context_for_job(user_id: str, workspace_id: str | None) -> DataAccessContext | None:
    if not workspace_id:
        return None
    user = get_user(user_id)
    if not user:
        raise PermissionError("Utilisateur du job introuvable.")
    role = workspace_role(user_id, workspace_id)
    if not role:
        raise PermissionError("L'utilisateur du job n'a plus accès au workspace.")
    ws = fetch_one("SELECT organization_id FROM workspaces WHERE id=:id", {"id": workspace_id}) or {}
    return DataAccessContext(
        user_id=user_id,
        email=user.get("email", ""),
        workspace_id=workspace_id,
        role=role,
        organization_id=ws.get("organization_id"),
    )
