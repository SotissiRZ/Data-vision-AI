from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.audit_service import record_event
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow
from app.services.operational_security import secret_rotation_status
from app.services.schema_migrations import migration_status

PRODUCT_VERSION = "2.69.0"
_SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _sha256_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _bool_control(control_id: str, name: str, desired: bool, observed: bool | None, evidence: str) -> dict[str, Any]:
    if observed is None:
        status = "unknown"
    elif observed == desired:
        status = "pass"
    else:
        status = "fail"
    return {
        "id": control_id,
        "name": name,
        "desired": desired,
        "observed": observed,
        "status": status,
        "evidence": evidence,
    }


def declared_runtime_posture() -> dict[str, Any]:
    settings = get_settings()
    return {
        "admission_signature_verification": bool(settings.admission_verify_images_enabled),
        "runtime_default_seccomp": bool(settings.runtime_security_seccomp_runtime_default),
        "run_as_non_root": bool(settings.runtime_security_run_as_non_root),
        "read_only_root_filesystem": bool(settings.runtime_security_read_only_root_filesystem),
        "drop_all_capabilities": bool(settings.runtime_security_drop_all_capabilities),
        "allow_privilege_escalation": False if settings.runtime_security_disallow_privilege_escalation else None,
        "runtime_detection_enabled": bool(settings.runtime_detection_enabled),
        "continuous_compliance_enabled": bool(settings.continuous_compliance_enabled),
    }


def _controls_from_observed(observed: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    desired = {
        "admission_signature_verification": True,
        "runtime_default_seccomp": True,
        "run_as_non_root": True,
        "read_only_root_filesystem": True,
        "drop_all_capabilities": True,
        "allow_privilege_escalation": False,
        "runtime_detection_enabled": True,
        "continuous_compliance_enabled": True,
    }
    actual = dict(observed or declared_runtime_posture())
    labels = {
        "admission_signature_verification": "Images signées vérifiées à l'admission",
        "runtime_default_seccomp": "Seccomp RuntimeDefault",
        "run_as_non_root": "Exécution non-root",
        "read_only_root_filesystem": "Root filesystem en lecture seule",
        "drop_all_capabilities": "Capabilities Linux supprimées",
        "allow_privilege_escalation": "Élévation de privilèges interdite",
        "runtime_detection_enabled": "Détection runtime activée",
        "continuous_compliance_enabled": "Conformité continue activée",
    }
    return [
        _bool_control(key, labels[key], wanted, actual.get(key), "configuration déclarée / observation soumise")
        for key, wanted in desired.items()
    ]


def run_compliance_scan(actor_id: str, *, workspace_id: str | None = None, observed: dict[str, Any] | None = None, source: str = "declared_configuration") -> dict[str, Any]:
    controls = _controls_from_observed(observed)
    drift = [item for item in controls if item["status"] == "fail"]
    unknown = [item for item in controls if item["status"] == "unknown"]
    status = "pass" if not drift and not unknown else "warn" if not drift else "fail"
    scan_id = str(uuid.uuid4())
    now = utcnow()
    payload = {
        "id": scan_id,
        "product_version": PRODUCT_VERSION,
        "workspace_id": workspace_id,
        "source": source,
        "status": status,
        "control_count": len(controls),
        "drift_count": len(drift),
        "unknown_count": len(unknown),
        "controls": controls,
        "scanned_at": now,
    }
    digest = _sha256_payload(payload)
    payload["sha256"] = digest
    execute(
        """INSERT INTO continuous_compliance_runs(id,workspace_id,status,source,control_count,drift_count,unknown_count,sha256,details_json,created_by,created_at)
           VALUES(:id,:workspace,:status,:source,:controls,:drift,:unknown,:sha,:details,:actor,:now)""",
        {"id": scan_id, "workspace": workspace_id, "status": status, "source": source, "controls": len(controls), "drift": len(drift),
         "unknown": len(unknown), "sha": digest, "details": json_dumps(payload), "actor": actor_id, "now": now},
    )
    record_event("compliance.continuous_scan", user_id=actor_id, workspace_id=workspace_id, resource_type="compliance_scan", resource_id=scan_id,
                 outcome="success" if status != "fail" else "failed", payload={"status": status, "drift_count": len(drift), "sha256": digest})
    return payload


def latest_compliance_scan(workspace_id: str | None = None) -> dict[str, Any] | None:
    if workspace_id:
        row = fetch_one("SELECT * FROM continuous_compliance_runs WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT 1", {"ws": workspace_id})
    else:
        row = fetch_one("SELECT * FROM continuous_compliance_runs ORDER BY created_at DESC LIMIT 1")
    if not row:
        return None
    details = json_loads(row.get("details_json", "{}"), {})
    details.setdefault("sha256", row.get("sha256"))
    return details


def list_compliance_scans(workspace_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(500, int(limit)))
    if workspace_id:
        rows = fetch_all("SELECT * FROM continuous_compliance_runs WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit", {"ws": workspace_id, "limit": limit})
    else:
        rows = fetch_all("SELECT * FROM continuous_compliance_runs ORDER BY created_at DESC LIMIT :limit", {"limit": limit})
    return [json_loads(row.get("details_json", "{}"), {}) for row in rows]


def record_runtime_security_event(actor_id: str, *, workspace_id: str | None, source: str, severity: str, rule: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    severity = severity.lower().strip()
    if severity not in _SEVERITY_ORDER:
        raise ValueError("Sévérité runtime invalide")
    event_id = str(uuid.uuid4())
    now = utcnow()
    item = {
        "id": event_id,
        "workspace_id": workspace_id,
        "source": source.strip()[:120],
        "severity": severity,
        "rule": rule.strip()[:240],
        "details": dict(details or {}),
        "created_at": now,
    }
    execute(
        """INSERT INTO runtime_security_events(id,workspace_id,source,severity,rule,details_json,created_by,created_at)
           VALUES(:id,:workspace,:source,:severity,:rule,:details,:actor,:now)""",
        {"id": event_id, "workspace": workspace_id, "source": item["source"], "severity": severity, "rule": item["rule"],
         "details": json_dumps(item["details"]), "actor": actor_id, "now": now},
    )
    record_event("security.runtime_event", user_id=actor_id, workspace_id=workspace_id, resource_type="runtime_security_event", resource_id=event_id,
                 outcome="failed" if _SEVERITY_ORDER[severity] >= _SEVERITY_ORDER["high"] else "success", payload={"source": item["source"], "severity": severity, "rule": item["rule"]})
    return item


def list_runtime_security_events(workspace_id: str | None = None, *, min_severity: str = "info", limit: int = 100) -> list[dict[str, Any]]:
    threshold = _SEVERITY_ORDER.get(min_severity.lower(), 0)
    limit = max(1, min(500, int(limit)))
    if workspace_id:
        rows = fetch_all("SELECT * FROM runtime_security_events WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit", {"ws": workspace_id, "limit": limit * 4})
    else:
        rows = fetch_all("SELECT * FROM runtime_security_events ORDER BY created_at DESC LIMIT :limit", {"limit": limit * 4})
    out: list[dict[str, Any]] = []
    for row in rows:
        severity = str(row.get("severity") or "info").lower()
        if _SEVERITY_ORDER.get(severity, 0) < threshold:
            continue
        out.append({
            "id": row.get("id"), "workspace_id": row.get("workspace_id"), "source": row.get("source"), "severity": severity,
            "rule": row.get("rule"), "details": json_loads(row.get("details_json", "{}"), {}), "created_at": row.get("created_at"),
        })
        if len(out) >= limit:
            break
    return out


def create_evidence_pack(actor_id: str, *, workspace_id: str | None = None) -> dict[str, Any]:
    latest = latest_compliance_scan(workspace_id) or run_compliance_scan(actor_id, workspace_id=workspace_id)
    runtime_events = list_runtime_security_events(workspace_id, min_severity="medium", limit=50)
    rotation = secret_rotation_status(workspace_id)
    migrations = migration_status()
    pack = {
        "format": "datavision-compliance-evidence-v1",
        "product_version": PRODUCT_VERSION,
        "workspace_id": workspace_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "continuous_compliance": latest,
        "runtime_security_events": runtime_events,
        "secret_rotation_summary": {
            "enabled": rotation.get("enabled"), "secret_count": rotation.get("secret_count"), "due_count": rotation.get("due_count"),
        },
        "schema_migrations": migrations,
    }
    digest = _sha256_payload(pack)
    pack_id = str(uuid.uuid4())
    pack["id"] = pack_id
    pack["sha256"] = digest
    root: Path = get_settings().data_root / "compliance_evidence"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"evidence-{pack_id}.json"
    path.write_text(json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    execute(
        """INSERT INTO compliance_evidence_packs(id,workspace_id,status,sha256,path,summary_json,created_by,created_at)
           VALUES(:id,:workspace,:status,:sha,:path,:summary,:actor,:now)""",
        {"id": pack_id, "workspace": workspace_id, "status": latest.get("status", "unknown"), "sha": digest, "path": str(path),
         "summary": json_dumps({"runtime_event_count": len(runtime_events), "drift_count": latest.get("drift_count", 0)}), "actor": actor_id, "now": utcnow()},
    )
    record_event("compliance.evidence_pack", user_id=actor_id, workspace_id=workspace_id, resource_type="compliance_evidence", resource_id=pack_id,
                 payload={"sha256": digest, "status": latest.get("status")})
    return pack


def list_evidence_packs(workspace_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(500, int(limit)))
    if workspace_id:
        rows = fetch_all("SELECT * FROM compliance_evidence_packs WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit", {"ws": workspace_id, "limit": limit})
    else:
        rows = fetch_all("SELECT * FROM compliance_evidence_packs ORDER BY created_at DESC LIMIT :limit", {"limit": limit})
    out=[]
    for row in rows:
        item=dict(row); item["summary"] = json_loads(item.pop("summary_json", "{}"), {}); out.append(item)
    return out
