from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.services.metadata_store import connection, execute, fetch_one, json_dumps, json_loads, utcnow


class EntitlementDenied(PermissionError):
    pass


class QuotaExceeded(PermissionError):
    pass


PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "starter": {
        "id": "starter",
        "label": "Starter",
        "features": {
            "ai_assistant": True,
            "notebooks": True,
            "connectors": True,
            "automl": False,
            "external_model_gateway": False,
            "enterprise_identity": False,
            "governed_actions": False,
        },
        "quotas": {
            "workspaces": 1,
            "members_per_workspace": 5,
            "datasets_per_workspace": 10,
            "connectors_per_workspace": 2,
            "notebooks_per_workspace": 10,
            "jobs_per_day": 20,
            "assistant_turns_per_day": 50,
        },
    },
    "pro": {
        "id": "pro",
        "label": "Pro",
        "features": {
            "ai_assistant": True,
            "notebooks": True,
            "connectors": True,
            "automl": True,
            "external_model_gateway": True,
            "enterprise_identity": False,
            "governed_actions": True,
        },
        "quotas": {
            "workspaces": 5,
            "members_per_workspace": 25,
            "datasets_per_workspace": 100,
            "connectors_per_workspace": 20,
            "notebooks_per_workspace": 100,
            "jobs_per_day": 500,
            "assistant_turns_per_day": 2000,
        },
    },
    "entreprise": {
        "id": "entreprise",
        "label": "Entreprise",
        "features": {
            "ai_assistant": True,
            "notebooks": True,
            "connectors": True,
            "automl": True,
            "external_model_gateway": True,
            "enterprise_identity": True,
            "governed_actions": True,
        },
        "quotas": {
            "workspaces": -1,
            "members_per_workspace": -1,
            "datasets_per_workspace": -1,
            "connectors_per_workspace": -1,
            "notebooks_per_workspace": -1,
            "jobs_per_day": -1,
            "assistant_turns_per_day": -1,
        },
    },
}


def plan_catalog() -> list[dict[str, Any]]:
    return [PLAN_CATALOG[key] for key in ("starter", "pro", "entreprise")]


def _normalize_plan(plan_id: str | None) -> str:
    value = str(plan_id or "").strip().lower()
    if value not in PLAN_CATALOG:
        raise ValueError(f"Plan produit inconnu: {value or '(vide)'}")
    return value


def _default_plan() -> str:
    configured = str(get_settings().default_product_plan or "entreprise").strip().lower()
    return configured if configured in PLAN_CATALOG else "entreprise"


def organization_plan(organization_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM organization_plan_assignments WHERE organization_id=:org",
        {"org": organization_id},
    )
    plan_id = _normalize_plan(row.get("plan_id") if row else _default_plan())
    plan = PLAN_CATALOG[plan_id]
    return {
        "organization_id": organization_id,
        "plan_id": plan_id,
        "label": plan["label"],
        "features": dict(plan["features"]),
        "quotas": dict(plan["quotas"]),
        "source": "assignment" if row else "default",
        "updated_at": row.get("updated_at") if row else None,
        "updated_by": row.get("updated_by") if row else None,
    }


def assign_organization_plan(organization_id: str, plan_id: str, *, actor_user_id: str | None = None) -> dict[str, Any]:
    plan_id = _normalize_plan(plan_id)
    now = utcnow()
    execute(
        """INSERT INTO organization_plan_assignments(organization_id,plan_id,updated_by,updated_at)
           VALUES(:org,:plan,:actor,:updated)
           ON CONFLICT(organization_id) DO UPDATE SET
             plan_id=excluded.plan_id,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
        {"org": organization_id, "plan": plan_id, "actor": actor_user_id, "updated": now},
    )
    return organization_plan(organization_id)


def _workspace_org(workspace_id: str) -> str:
    row = fetch_one("SELECT organization_id FROM workspaces WHERE id=:ws", {"ws": workspace_id})
    if not row:
        raise KeyError("Workspace introuvable")
    return str(row["organization_id"])


def workspace_plan(workspace_id: str) -> dict[str, Any]:
    out = organization_plan(_workspace_org(workspace_id))
    out["workspace_id"] = workspace_id
    return out


def assert_feature(workspace_id: str, feature: str) -> dict[str, Any]:
    plan = workspace_plan(workspace_id)
    if not bool((plan.get("features") or {}).get(feature, False)):
        raise EntitlementDenied(
            f"La fonctionnalité « {feature} » n'est pas incluse dans le plan {plan['label']}."
        )
    return plan


def _quota_limit_for_workspace(workspace_id: str, quota: str) -> tuple[dict[str, Any], int]:
    plan = workspace_plan(workspace_id)
    quotas = plan.get("quotas") or {}
    if quota not in quotas:
        raise ValueError(f"Quota inconnu: {quota}")
    return plan, int(quotas[quota])


def _quota_limit_for_org(organization_id: str, quota: str) -> tuple[dict[str, Any], int]:
    plan = organization_plan(organization_id)
    quotas = plan.get("quotas") or {}
    if quota not in quotas:
        raise ValueError(f"Quota inconnu: {quota}")
    return plan, int(quotas[quota])


def _check_count(limit: int, current: int, increment: int, *, label: str, plan_label: str) -> None:
    if limit >= 0 and current + increment > limit:
        raise QuotaExceeded(
            f"Quota {label} atteint pour le plan {plan_label}: {current}/{limit}."
        )


def assert_organization_workspace_quota(organization_id: str, *, increment: int = 1) -> None:
    plan, limit = _quota_limit_for_org(organization_id, "workspaces")
    current = int((fetch_one(
        "SELECT COUNT(*) AS n FROM workspaces WHERE organization_id=:org", {"org": organization_id}
    ) or {"n": 0})["n"])
    _check_count(limit, current, increment, label="workspaces", plan_label=plan["label"])


def assert_workspace_resource_quota(workspace_id: str, resource: str, *, increment: int = 1) -> None:
    mapping = {
        "members": ("members_per_workspace", "workspace_members", "workspace_id"),
        "datasets": ("datasets_per_workspace", "workspace_datasets", "workspace_id"),
        "connectors": ("connectors_per_workspace", "data_connectors", "workspace_id"),
        "notebooks": ("notebooks_per_workspace", "notebook_documents", "scope_id"),
    }
    if resource not in mapping:
        raise ValueError(f"Ressource de quota inconnue: {resource}")
    quota, table, column = mapping[resource]
    plan, limit = _quota_limit_for_workspace(workspace_id, quota)
    if resource == "notebooks":
        row = fetch_one(
            f"SELECT COUNT(*) AS n FROM {table} WHERE scope_type='workspace' AND {column}=:ws",
            {"ws": workspace_id},
        )
    else:
        row = fetch_one(f"SELECT COUNT(*) AS n FROM {table} WHERE {column}=:ws", {"ws": workspace_id})
    current = int((row or {"n": 0})["n"])
    _check_count(limit, current, increment, label=resource, plan_label=plan["label"])


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def consume_daily_quota(workspace_id: str, metric: str, *, amount: int = 1) -> dict[str, Any]:
    if amount <= 0:
        raise ValueError("amount doit être > 0")
    quota_map = {
        "jobs": "jobs_per_day",
        "assistant_turns": "assistant_turns_per_day",
    }
    quota_name = quota_map.get(metric)
    if not quota_name:
        raise ValueError(f"Métrique de quota inconnue: {metric}")
    plan, limit = _quota_limit_for_workspace(workspace_id, quota_name)
    day = _today_utc()
    now = utcnow()
    with connection() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                """INSERT INTO plan_usage_daily(workspace_id,metric,usage_date,amount,updated_at)
                   VALUES(:ws,:metric,:day,0,:updated)
                   ON CONFLICT(workspace_id,metric,usage_date) DO NOTHING"""
            ),
            {"ws": workspace_id, "metric": metric, "day": day, "updated": now},
        )
        stmt = __import__("sqlalchemy").text(
            """UPDATE plan_usage_daily SET amount=amount+:delta,updated_at=:updated
               WHERE workspace_id=:ws AND metric=:metric AND usage_date=:day
               AND (:limit_value < 0 OR amount+:delta <= :limit_value)"""
        )
        result = conn.execute(
            stmt,
            {"delta": int(amount), "updated": now, "ws": workspace_id, "metric": metric, "day": day, "limit_value": limit},
        )
        if int(result.rowcount or 0) != 1:
            current_row = conn.execute(
                __import__("sqlalchemy").text(
                    "SELECT amount FROM plan_usage_daily WHERE workspace_id=:ws AND metric=:metric AND usage_date=:day"
                ),
                {"ws": workspace_id, "metric": metric, "day": day},
            ).mappings().first()
            current = int((current_row or {"amount": 0})["amount"])
            raise QuotaExceeded(
                f"Quota {quota_name} atteint pour le plan {plan['label']}: {current}/{limit}."
            )
    return daily_usage(workspace_id, metric)


def daily_usage(workspace_id: str, metric: str) -> dict[str, Any]:
    plan, limit = _quota_limit_for_workspace(workspace_id, {
        "jobs": "jobs_per_day",
        "assistant_turns": "assistant_turns_per_day",
    }[metric])
    row = fetch_one(
        "SELECT amount,updated_at FROM plan_usage_daily WHERE workspace_id=:ws AND metric=:metric AND usage_date=:day",
        {"ws": workspace_id, "metric": metric, "day": _today_utc()},
    ) or {"amount": 0, "updated_at": None}
    amount = int(row["amount"] or 0)
    return {
        "workspace_id": workspace_id,
        "metric": metric,
        "date": _today_utc(),
        "used": amount,
        "limit": limit,
        "remaining": None if limit < 0 else max(limit - amount, 0),
        "plan_id": plan["plan_id"],
        "updated_at": row.get("updated_at"),
    }


def workspace_plan_status(workspace_id: str) -> dict[str, Any]:
    plan = workspace_plan(workspace_id)
    try:
        notebook_count = int((fetch_one("SELECT COUNT(*) AS n FROM notebook_documents WHERE scope_type='workspace' AND scope_id=:ws", {"ws": workspace_id}) or {"n": 0})["n"])
    except Exception:
        notebook_count = 0
    counts = {
        "members": int((fetch_one("SELECT COUNT(*) AS n FROM workspace_members WHERE workspace_id=:ws", {"ws": workspace_id}) or {"n": 0})["n"]),
        "datasets": int((fetch_one("SELECT COUNT(*) AS n FROM workspace_datasets WHERE workspace_id=:ws", {"ws": workspace_id}) or {"n": 0})["n"]),
        "connectors": int((fetch_one("SELECT COUNT(*) AS n FROM data_connectors WHERE workspace_id=:ws", {"ws": workspace_id}) or {"n": 0})["n"]),
        "notebooks": notebook_count,
    }
    return {
        **plan,
        "resource_usage": counts,
        "daily_usage": {
            "jobs": daily_usage(workspace_id, "jobs"),
            "assistant_turns": daily_usage(workspace_id, "assistant_turns"),
        },
        "policy": "fail-closed on disabled entitlements and finite quotas; default plan preserves backward compatibility",
    }
