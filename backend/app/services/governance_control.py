from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from app.assistant.ai_settings import get_ai_settings, list_provider_profiles, monthly_usage
from app.services.audit_service import list_events, record_event
from app.services.auth_service import ROLES, workspace_role
from app.services.collaboration import list_certifications, review_summary
from app.services.data_reliability import build_lineage_graph, publication_gate, reliability_summary
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow
from app.services.model_registry import registry_summary
from app.services.storage import load_dataframe
from app.services.trust_center import trust_center
from app.services.workspace_service import (
    get_workspace, list_members, list_policies, list_workspace_datasets, policies_for_access,
)


def _ensure_tables() -> None:
    execute("""CREATE TABLE IF NOT EXISTS governance_snapshots (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        dataset_id TEXT,
        created_by TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _role_matrix(user_id: str, workspace_id: str, dataset_id: str) -> list[dict[str, Any]]:
    df = load_dataframe(dataset_id)
    all_columns = [str(c) for c in df.columns]
    rows: list[dict[str, Any]] = []
    for role in ROLES:
        policies = policies_for_access(user_id, workspace_id, dataset_id, role_override=role)
        column_sets = [set(map(str, p.get("allowed_columns") or [])) for p in policies if p.get("allowed_columns")]
        allowed = sorted(set.intersection(*column_sets)) if column_sets else list(all_columns)
        row_rules = [rule for policy in policies for rule in (policy.get("row_filters") or [])]
        rows.append({
            "role": role,
            "policy_count": len(policies),
            "allowed_columns": allowed,
            "allowed_column_count": len(allowed),
            "total_column_count": len(all_columns),
            "row_filter_count": len(row_rules),
            "restricted": bool(column_sets or row_rules),
        })
    return rows


def _active_dataset_certifications(user_id: str, workspace_id: str, dataset_id: str) -> list[dict[str, Any]]:
    result = []
    for cert in list_certifications(user_id, workspace_id, status="active"):
        if str(cert.get("dataset_id") or "") == str(dataset_id) or (
            cert.get("resource_type") == "dataset" and str(cert.get("resource_id")) == str(dataset_id)
        ):
            result.append(cert)
    return result


def _control(status: str, control_id: str, name: str, evidence: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": control_id, "name": name, "status": status, "evidence": evidence, "details": details or {}}


def control_plane_overview(user_id: str, workspace_id: str, dataset_id: str | None = None) -> dict[str, Any]:
    role = workspace_role(user_id, workspace_id)
    if not role:
        raise PermissionError("Accès au workspace refusé.")
    workspace = get_workspace(user_id, workspace_id)
    members = list_members(user_id, workspace_id)
    datasets = list_workspace_datasets(user_id, workspace_id)
    if dataset_id:
        bound_ids = {str(x.get("dataset_id")) for x in datasets}
        if str(dataset_id) not in bound_ids:
            raise PermissionError("Ce dataset n'est pas lié au workspace actif.")
    policies = list_policies(user_id, workspace_id)
    audits = list_events(workspace_id=workspace_id, limit=200)
    review = review_summary(user_id, workspace_id)
    models = registry_summary(workspace_id)
    lineage = build_lineage_graph(workspace_id, dataset_id)
    reliability = reliability_summary(workspace_id, dataset_id)
    ai = get_ai_settings("workspace", workspace_id)
    providers = list_provider_profiles("workspace", workspace_id)
    usage = monthly_usage("workspace", workspace_id)

    dataset_payload: dict[str, Any] | None = None
    controls = [
        _control("pass" if members else "warn", "identity_rbac", "Identité & RBAC", f"{len(members)} membre(s), rôle actif {role}"),
        _control("pass" if datasets else "warn", "dataset_binding", "Datasets gouvernés", f"{len(datasets)} dataset(s) lié(s)"),
        _control("pass" if policies else "warn", "access_policies", "RLS / sécurité colonne", f"{len(policies)} politique(s) active(s)"),
        _control("pass" if audits else "warn", "audit_trail", "Journal d'audit", f"{len(audits)} événement(s) récents"),
        _control("pass" if lineage.get("node_count", 0) else "warn", "lineage", "Lineage", f"{lineage.get('node_count',0)} nœud(s), {lineage.get('edge_count',0)} relation(s)"),
    ]

    enabled_providers = [p for p in providers if p.enabled]
    ai_ok = ai.planner_mode == "deterministic" or bool(enabled_providers)
    controls.append(_control(
        "pass" if ai_ok else "fail", "ai_governance", "Politique IA",
        f"planner={ai.planner_mode}, confidentialité={ai.privacy_mode}, {len(enabled_providers)} provider(s) actif(s)",
        {"allow_external_ai": ai.allow_external_ai, "fallback_to_deterministic": ai.fallback_to_deterministic},
    ))
    controls.append(_control(
        "warn" if models.get("degraded_monitoring_runs") else "pass", "model_governance", "Gouvernance modèles",
        f"{models.get('total_models',0)} modèle(s), {models.get('degraded_monitoring_runs',0)} run(s) dégradé(s)",
    ))

    if dataset_id:
        frame = load_dataframe(dataset_id)
        trust = trust_center(dataset_id, frame)
        publication = publication_gate(workspace_id, dataset_id)
        certifications = _active_dataset_certifications(user_id, workspace_id, dataset_id)
        matrix = _role_matrix(user_id, workspace_id, dataset_id)
        reliability_status = "fail" if publication.get("blockers") else ("warn" if publication.get("warnings") else "pass")
        controls.extend([
            _control(reliability_status, "publication_gate", "Publication gate", "Publication autorisée" if publication.get("allowed") else f"{len(publication.get('blockers') or [])} bloqueur(s)"),
            _control("pass" if certifications else "warn", "certification", "Certification", f"{len(certifications)} certification(s) active(s)"),
            _control("pass" if int(trust.get("overall_score", 0)) >= 70 else "warn", "trust", "Trust Center", f"Trust {trust.get('overall_score',0)}/100 · {trust.get('grade','—')}"),
        ])
        dataset_payload = {
            "dataset_id": dataset_id,
            "trust": trust,
            "publication": publication,
            "certifications": certifications,
            "role_matrix": matrix,
        }

    pass_count = sum(1 for c in controls if c["status"] == "pass")
    fail_count = sum(1 for c in controls if c["status"] == "fail")
    coverage = round(100 * pass_count / max(1, len(controls)), 1)
    audit_core = [{k: e.get(k) for k in ("id", "event_type", "resource_type", "resource_id", "outcome", "created_at")} for e in audits]
    audit_digest = _digest(audit_core)
    return {
        "workspace": {"id": workspace_id, "name": workspace.get("name"), "role": role},
        "generated_at": utcnow(),
        "control_coverage_percent": coverage,
        "control_status": "blocked" if fail_count else ("attention" if any(c["status"] == "warn" for c in controls) else "healthy"),
        "controls": controls,
        "summary": {
            "members": len(members), "datasets": len(datasets), "policies": len(policies),
            "audit_events": len(audits), "reviews": review, "models": models,
            "lineage": {"nodes": lineage.get("node_count",0), "edges": lineage.get("edge_count",0)},
            "reliability": reliability,
        },
        "ai": {
            "settings": ai.model_dump(mode="json"),
            "providers": [{"id": p.id, "name": p.name, "provider_type": p.provider_type, "location": p.location, "model": p.model, "enabled": p.enabled} for p in providers],
            "monthly_usage": usage,
        },
        "audit_digest_sha256": audit_digest,
        "dataset": dataset_payload,
    }


def capture_governance_snapshot(user_id: str, workspace_id: str, dataset_id: str | None = None) -> dict[str, Any]:
    _ensure_tables()
    overview = control_plane_overview(user_id, workspace_id, dataset_id)
    snapshot_id = str(uuid.uuid4())
    created = utcnow()
    payload = {**overview, "snapshot_id": snapshot_id, "captured_at": created}
    sha = _digest(payload)
    execute(
        "INSERT INTO governance_snapshots(id,workspace_id,dataset_id,created_by,payload_json,sha256,created_at) VALUES(:id,:ws,:ds,:user,:payload,:sha,:created)",
        {"id": snapshot_id, "ws": workspace_id, "ds": dataset_id, "user": user_id, "payload": json_dumps(payload), "sha": sha, "created": created},
    )
    record_event("governance.snapshot.capture", user_id=user_id, workspace_id=workspace_id, resource_type="governance_snapshot", resource_id=snapshot_id, payload={"dataset_id": dataset_id, "sha256": sha})
    return {"id": snapshot_id, "workspace_id": workspace_id, "dataset_id": dataset_id, "sha256": sha, "created_at": created, "payload": payload}


def list_governance_snapshots(user_id: str, workspace_id: str, limit: int = 30) -> list[dict[str, Any]]:
    if not workspace_role(user_id, workspace_id):
        raise PermissionError("Accès au workspace refusé.")
    _ensure_tables()
    rows = fetch_all("SELECT * FROM governance_snapshots WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit", {"ws": workspace_id, "limit": max(1, min(limit, 200))})
    result = []
    for row in rows:
        payload = json_loads(row.pop("payload_json", "{}"), {})
        row["control_coverage_percent"] = payload.get("control_coverage_percent")
        row["control_status"] = payload.get("control_status")
        result.append(row)
    return result
