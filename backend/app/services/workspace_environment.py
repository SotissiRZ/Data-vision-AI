from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.services.audit_service import record_event
from app.services.auth_service import has_permission
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow
from app.services.notebook_sandbox import close_kernel_session, sandbox_packages
from app.services.tenant_access import current_access_context

LOCAL_SCOPE_ID = "__local__"
_PACKAGE_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\s*(?:==|>=|<=|~=|>|<)\s*[A-Za-z0-9_.+!-]+)?$")
_DEFAULT_POLICY = {
    "install_mode": "image-managed",
    "dynamic_install": False,
    "network_install": False,
    "isolation": "workspace-sandbox",
    "inheritance": "workspace-default+notebook-overlay",
}


def _ensure_table() -> None:
    execute(
        """CREATE TABLE IF NOT EXISTS workspace_runtime_environments (
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            python_requirements_json TEXT NOT NULL,
            r_requirements_json TEXT NOT NULL,
            python_lock_json TEXT NOT NULL,
            r_lock_json TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            fingerprint_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            policy_json TEXT NOT NULL,
            inventory_sha256 TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            synced_at TEXT,
            PRIMARY KEY(scope_type, scope_id)
        )"""
    )


def _scope(*, require_manage: bool = False) -> tuple[str, str, str | None]:
    ctx = current_access_context()
    if ctx is None:
        return "local", LOCAL_SCOPE_ID, None
    if require_manage and not has_permission(ctx.user_id, ctx.workspace_id, "workspace:manage"):
        raise PermissionError("Permission insuffisante: workspace:manage.")
    return "workspace", ctx.workspace_id, ctx.user_id


def _normalize_requirements(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in values or []:
        value = str(raw or "").strip()
        if not value:
            continue
        if len(value) > 120 or not _PACKAGE_RE.fullmatch(value):
            raise ValueError(f"Exigence package invalide: {value[:80]}")
        if value not in normalized:
            normalized.append(value)
    return normalized[:150]


def _requirement_name(value: str) -> str:
    return re.split(r"\s*(?:==|>=|<=|~=|>|<)\s*", value.strip(), maxsplit=1)[0].lower()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _inventory_digest(inventory: dict[str, Any]) -> str:
    payload = {
        "python": dict(sorted((inventory.get("python") or {}).items())),
        "r": dict(sorted((inventory.get("r") or {}).items())),
        "install_policy": inventory.get("install_policy", "image-managed"),
        "dynamic_install": bool(inventory.get("dynamic_install", False)),
    }
    return _fingerprint(payload)


def _manifest(
    *,
    scope_type: str,
    scope_id: str,
    python_requirements: list[str],
    r_requirements: list[str],
    python_lock: dict[str, str],
    r_lock: dict[str, str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "datavision.workspace-environment/v1",
        "scope": {"type": scope_type, "id": scope_id},
        "python": {
            "requirements": list(python_requirements),
            "lock": dict(sorted(python_lock.items())),
        },
        "r": {
            "requirements": list(r_requirements),
            "lock": dict(sorted(r_lock.items())),
        },
        "policy": {
            "install_mode": policy.get("install_mode", "image-managed"),
            "dynamic_install": bool(policy.get("dynamic_install", False)),
            "network_install": bool(policy.get("network_install", False)),
            "isolation": policy.get("isolation", "workspace-sandbox"),
            "inheritance": policy.get("inheritance", "workspace-default+notebook-overlay"),
        },
    }


def _create_default(scope_type: str, scope_id: str, actor: str | None) -> dict[str, Any]:
    now = utcnow()
    manifest = _manifest(
        scope_type=scope_type,
        scope_id=scope_id,
        python_requirements=[],
        r_requirements=[],
        python_lock={},
        r_lock={},
        policy=_DEFAULT_POLICY,
    )
    execute(
        """INSERT INTO workspace_runtime_environments(
            scope_type,scope_id,python_requirements_json,r_requirements_json,
            python_lock_json,r_lock_json,manifest_json,fingerprint_sha256,status,
            policy_json,inventory_sha256,created_by,created_at,updated_at,synced_at
        ) VALUES(
            :scope_type,:scope_id,'[]','[]','{}','{}',:manifest,:fingerprint,'unsynced',
            :policy,NULL,:actor,:created,:updated,NULL
        )""",
        {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "manifest": json_dumps(manifest),
            "fingerprint": _fingerprint(manifest),
            "policy": json_dumps(_DEFAULT_POLICY),
            "actor": actor,
            "created": now,
            "updated": now,
        },
    )
    row = fetch_one(
        "SELECT * FROM workspace_runtime_environments WHERE scope_type=:scope_type AND scope_id=:scope_id",
        {"scope_type": scope_type, "scope_id": scope_id},
    )
    assert row is not None
    return row


def _row(*, create: bool = True) -> dict[str, Any] | None:
    _ensure_table()
    scope_type, scope_id, actor = _scope()
    row = fetch_one(
        "SELECT * FROM workspace_runtime_environments WHERE scope_type=:scope_type AND scope_id=:scope_id",
        {"scope_type": scope_type, "scope_id": scope_id},
    )
    if row or not create:
        return row
    return _create_default(scope_type, scope_id, actor)


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    manifest = json_loads(row.get("manifest_json"), {})
    return {
        "scope_type": row["scope_type"],
        "scope_id": row["scope_id"],
        "python_requirements": json_loads(row.get("python_requirements_json"), []),
        "r_requirements": json_loads(row.get("r_requirements_json"), []),
        "python_lock": json_loads(row.get("python_lock_json"), {}),
        "r_lock": json_loads(row.get("r_lock_json"), {}),
        "manifest": manifest,
        "fingerprint_sha256": row.get("fingerprint_sha256") or _fingerprint(manifest),
        "inventory_sha256": row.get("inventory_sha256"),
        "status": row.get("status") or "unsynced",
        "policy": json_loads(row.get("policy_json"), dict(_DEFAULT_POLICY)),
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "synced_at": row.get("synced_at"),
        "reproducible": bool(row.get("status") == "ready" and row.get("fingerprint_sha256")),
    }


def get_workspace_environment() -> dict[str, Any]:
    row = _row(create=True)
    assert row is not None
    return _payload(row)


def workspace_environment_snapshot() -> dict[str, Any]:
    """Read-only snapshot used by notebook provenance without requiring sandbox access."""
    return get_workspace_environment()


def _invalidate_workspace_kernels(scope_type: str, scope_id: str) -> int:
    try:
        rows = fetch_all(
            """SELECT ks.notebook_id,ks.language,ks.session_id
               FROM notebook_kernel_sessions ks
               JOIN notebook_documents nd ON nd.id=ks.notebook_id
               WHERE nd.scope_type=:scope_type AND nd.scope_id=:scope_id""",
            {"scope_type": scope_type, "scope_id": scope_id},
        )
    except Exception:
        rows = []
    now = utcnow()
    for item in rows:
        try:
            close_kernel_session(str(item.get("session_id") or ""))
        except Exception:
            pass
        execute(
            """UPDATE notebook_kernel_sessions
               SET state_status='reset',execution_count=0,last_seen_at=:seen
               WHERE notebook_id=:notebook AND language=:language""",
            {
                "seen": now,
                "notebook": item["notebook_id"],
                "language": item["language"],
            },
        )
    return len(rows)


def update_workspace_environment(
    *,
    python_requirements: list[str] | None = None,
    r_requirements: list[str] | None = None,
) -> dict[str, Any]:
    scope_type, scope_id, actor = _scope(require_manage=True)
    row = _row(create=True)
    assert row is not None
    python = (
        _normalize_requirements(python_requirements)
        if python_requirements is not None
        else json_loads(row.get("python_requirements_json"), [])
    )
    r = (
        _normalize_requirements(r_requirements)
        if r_requirements is not None
        else json_loads(row.get("r_requirements_json"), [])
    )
    policy = json_loads(row.get("policy_json"), dict(_DEFAULT_POLICY))
    manifest = _manifest(
        scope_type=scope_type,
        scope_id=scope_id,
        python_requirements=python,
        r_requirements=r,
        python_lock={},
        r_lock={},
        policy=policy,
    )
    fingerprint = _fingerprint(manifest)
    execute(
        """UPDATE workspace_runtime_environments
           SET python_requirements_json=:python,r_requirements_json=:r,
               python_lock_json='{}',r_lock_json='{}',manifest_json=:manifest,
               fingerprint_sha256=:fingerprint,status='unsynced',inventory_sha256=NULL,
               updated_at=:updated,synced_at=NULL
           WHERE scope_type=:scope_type AND scope_id=:scope_id""",
        {
            "python": json_dumps(python),
            "r": json_dumps(r),
            "manifest": json_dumps(manifest),
            "fingerprint": fingerprint,
            "updated": utcnow(),
            "scope_type": scope_type,
            "scope_id": scope_id,
        },
    )
    invalidated = _invalidate_workspace_kernels(scope_type, scope_id)
    record_event(
        "workspace.environment_update",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="workspace_environment",
        resource_id=scope_id,
        payload={
            "python_requirements": python,
            "r_requirements": r,
            "fingerprint_sha256": fingerprint,
            "invalidated_kernels": invalidated,
            "dynamic_install": False,
        },
    )
    return get_workspace_environment()


def _resolve_lock(requirements: list[str], inventory: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    normalized_inventory = {str(k).lower(): str(v) for k, v in inventory.items()}
    lock: dict[str, str] = {}
    missing: list[str] = []
    for requirement in requirements:
        name = _requirement_name(requirement)
        version = normalized_inventory.get(name)
        if version is None:
            missing.append(requirement)
        else:
            lock[name] = version
    return lock, missing


def sync_workspace_environment() -> dict[str, Any]:
    scope_type, scope_id, actor = _scope(require_manage=True)
    row = _row(create=True)
    assert row is not None
    current = _payload(row)
    inventory = sandbox_packages()
    python_lock, missing_python = _resolve_lock(
        current["python_requirements"], inventory.get("python") or {}
    )
    r_lock, missing_r = _resolve_lock(
        current["r_requirements"], inventory.get("r") or {}
    )
    policy = current["policy"]
    manifest = _manifest(
        scope_type=scope_type,
        scope_id=scope_id,
        python_requirements=current["python_requirements"],
        r_requirements=current["r_requirements"],
        python_lock=python_lock,
        r_lock=r_lock,
        policy=policy,
    )
    fingerprint = _fingerprint(manifest)
    status = "ready" if not missing_python and not missing_r else "missing_packages"
    now = utcnow()
    changed = fingerprint != current.get("fingerprint_sha256")
    execute(
        """UPDATE workspace_runtime_environments
           SET python_lock_json=:python_lock,r_lock_json=:r_lock,manifest_json=:manifest,
               fingerprint_sha256=:fingerprint,status=:status,inventory_sha256=:inventory,
               updated_at=:updated,synced_at=:synced
           WHERE scope_type=:scope_type AND scope_id=:scope_id""",
        {
            "python_lock": json_dumps(python_lock),
            "r_lock": json_dumps(r_lock),
            "manifest": json_dumps(manifest),
            "fingerprint": fingerprint,
            "status": status,
            "inventory": _inventory_digest(inventory),
            "updated": now,
            "synced": now,
            "scope_type": scope_type,
            "scope_id": scope_id,
        },
    )
    invalidated = _invalidate_workspace_kernels(scope_type, scope_id) if changed else 0
    record_event(
        "workspace.environment_sync",
        user_id=actor,
        workspace_id=scope_id if scope_type == "workspace" else None,
        resource_type="workspace_environment",
        resource_id=scope_id,
        outcome="success" if status == "ready" else "warning",
        payload={
            "status": status,
            "fingerprint_sha256": fingerprint,
            "missing_python": missing_python,
            "missing_r": missing_r,
            "invalidated_kernels": invalidated,
        },
    )
    return {
        **get_workspace_environment(),
        "missing_python": missing_python,
        "missing_r": missing_r,
        "inventory_policy": inventory.get("install_policy", "image-managed"),
        "dynamic_install": bool(inventory.get("dynamic_install", False)),
    }


def verify_workspace_environment() -> dict[str, Any]:
    current = get_workspace_environment()
    manifest = current.get("manifest") or {}
    manifest_ok = _fingerprint(manifest) == current.get("fingerprint_sha256")
    inventory = sandbox_packages()
    python_inventory = {str(k).lower(): str(v) for k, v in (inventory.get("python") or {}).items()}
    r_inventory = {str(k).lower(): str(v) for k, v in (inventory.get("r") or {}).items()}
    drift: list[dict[str, str | None]] = []
    for language, lock, available in (
        ("python", current.get("python_lock") or {}, python_inventory),
        ("r", current.get("r_lock") or {}, r_inventory),
    ):
        for package, expected in lock.items():
            actual = available.get(str(package).lower())
            if actual != str(expected):
                drift.append({
                    "language": language,
                    "package": str(package),
                    "expected": str(expected),
                    "actual": actual,
                })
    inventory_ok = _inventory_digest(inventory) == current.get("inventory_sha256") if current.get("inventory_sha256") else False
    return {
        **current,
        "verified": bool(manifest_ok and not drift and current.get("status") == "ready"),
        "manifest_integrity": manifest_ok,
        "inventory_matches_sync": inventory_ok,
        "lock_drift": drift,
    }


def merge_requirements(workspace_values: list[str], notebook_values: list[str]) -> list[str]:
    """Merge workspace defaults with notebook overlays without allowing version ambiguity."""
    merged: dict[str, str] = {}
    order: list[str] = []
    for requirement in [*workspace_values, *notebook_values]:
        name = _requirement_name(requirement)
        if name not in merged:
            order.append(name)
        merged[name] = requirement
    return [merged[name] for name in order]
