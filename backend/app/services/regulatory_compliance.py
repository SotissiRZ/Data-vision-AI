from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.audit_service import record_event
from app.services.continuous_compliance import latest_compliance_scan, run_compliance_scan
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow

PRODUCT_VERSION = "2.69.0"
CATALOG_VERSION = "2026.09-v1"

FRAMEWORKS: list[dict[str, Any]] = [
    {
        "id": "datavision-baseline",
        "name": "DataVision Security Baseline",
        "version": "2.65",
        "mapping_level": "native-control",
        "disclaimer": "Référentiel technique interne DataVision.",
    },
    {
        "id": "nist-csf-2.0",
        "name": "NIST Cybersecurity Framework",
        "version": "2.0",
        "mapping_level": "control-family",
        "disclaimer": "Correspondance de familles de contrôles, pas une certification ni une évaluation NIST officielle.",
    },
    {
        "id": "iso27001-2022",
        "name": "ISO/IEC 27001",
        "version": "2022",
        "mapping_level": "control-family",
        "disclaimer": "Correspondance technique indicative avec des familles de contrôles; ne constitue pas une certification ISO.",
    },
    {
        "id": "soc2-security",
        "name": "SOC 2 - Security",
        "version": "Trust Services Criteria",
        "mapping_level": "control-family",
        "disclaimer": "Correspondance de posture technique; ne constitue pas un rapport SOC 2 ni une opinion d'audit.",
    },
]

_CONTROL_SPECS: list[dict[str, Any]] = [
    {
        "id": "DV-ADM-001",
        "source_control": "admission_signature_verification",
        "name": "Vérification des images signées à l'admission",
        "category": "supply_chain",
        "frameworks": {"datavision-baseline": "Admission", "nist-csf-2.0": "Protect / Platform Security", "iso27001-2022": "Technology controls", "soc2-security": "Logical access and change management"},
        "remediation": "Activer la vérification d'images signées et imposer des références immuables par digest.",
        "verification": "Rendre le chart et vérifier que la policy d'admission bloque une image non signée de test.",
    },
    {
        "id": "DV-RUN-001",
        "source_control": "runtime_default_seccomp",
        "name": "Seccomp RuntimeDefault",
        "category": "runtime",
        "frameworks": {"datavision-baseline": "Runtime", "nist-csf-2.0": "Protect / Platform Security", "iso27001-2022": "Technology controls", "soc2-security": "System operations"},
        "remediation": "Définir seccompProfile.type=RuntimeDefault pour les workloads DataVision.",
        "verification": "Inspecter les securityContext rendus et lancer le gate runtime security.",
    },
    {
        "id": "DV-RUN-002",
        "source_control": "run_as_non_root",
        "name": "Exécution non-root",
        "category": "runtime",
        "frameworks": {"datavision-baseline": "Runtime", "nist-csf-2.0": "Protect / Platform Security", "iso27001-2022": "Technology controls", "soc2-security": "System operations"},
        "remediation": "Forcer runAsNonRoot et un UID non privilégié pour chaque conteneur applicatif.",
        "verification": "Vérifier le securityContext Kubernetes et l'UID effectif dans un pod de validation.",
    },
    {
        "id": "DV-RUN-003",
        "source_control": "read_only_root_filesystem",
        "name": "Root filesystem en lecture seule",
        "category": "runtime",
        "frameworks": {"datavision-baseline": "Runtime", "nist-csf-2.0": "Protect / Platform Security", "iso27001-2022": "Technology controls", "soc2-security": "System operations"},
        "remediation": "Activer readOnlyRootFilesystem et monter uniquement les volumes d'écriture nécessaires.",
        "verification": "Tester une écriture hors volumes autorisés dans un environnement de test.",
    },
    {
        "id": "DV-RUN-004",
        "source_control": "drop_all_capabilities",
        "name": "Capabilities Linux supprimées",
        "category": "runtime",
        "frameworks": {"datavision-baseline": "Runtime", "nist-csf-2.0": "Protect / Platform Security", "iso27001-2022": "Technology controls", "soc2-security": "System operations"},
        "remediation": "Configurer capabilities.drop=[ALL] et réajouter uniquement une capability explicitement justifiée.",
        "verification": "Inspecter les securityContext rendus et le profil effectif du conteneur.",
    },
    {
        "id": "DV-RUN-005",
        "source_control": "allow_privilege_escalation",
        "name": "Élévation de privilèges interdite",
        "category": "runtime",
        "frameworks": {"datavision-baseline": "Runtime", "nist-csf-2.0": "Protect / Platform Security", "iso27001-2022": "Technology controls", "soc2-security": "System operations"},
        "remediation": "Configurer allowPrivilegeEscalation=false sur tous les conteneurs applicatifs.",
        "verification": "Vérifier les manifests rendus et les policies d'admission.",
    },
    {
        "id": "DV-DET-001",
        "source_control": "runtime_detection_enabled",
        "name": "Détection runtime activée",
        "category": "detection",
        "frameworks": {"datavision-baseline": "Detection", "nist-csf-2.0": "Detect", "iso27001-2022": "Monitoring activities", "soc2-security": "System monitoring"},
        "remediation": "Activer la détection runtime et raccorder les événements à l'API DataVision ou au SIEM.",
        "verification": "Injecter un événement de test et vérifier sa présence dans le journal runtime.",
    },
    {
        "id": "DV-COM-001",
        "source_control": "continuous_compliance_enabled",
        "name": "Conformité continue activée",
        "category": "governance",
        "frameworks": {"datavision-baseline": "Continuous compliance", "nist-csf-2.0": "Govern", "iso27001-2022": "Internal review and monitoring", "soc2-security": "Monitoring activities"},
        "remediation": "Activer les scans de conformité périodiques et conserver l'historique des résultats.",
        "verification": "Exécuter un scan et vérifier l'enregistrement du snapshot et de son SHA-256.",
    },
]


def _sha256_payload(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def control_catalog(framework_id: str | None = None) -> dict[str, Any]:
    framework_ids = {item["id"] for item in FRAMEWORKS}
    if framework_id and framework_id not in framework_ids:
        raise ValueError("Framework de conformité inconnu")
    controls = []
    for spec in _CONTROL_SPECS:
        if framework_id and framework_id not in spec["frameworks"]:
            continue
        item = dict(spec)
        item["framework_mapping"] = dict(spec["frameworks"])
        item.pop("frameworks", None)
        controls.append(item)
    return {
        "catalog_version": CATALOG_VERSION,
        "product_version": PRODUCT_VERSION,
        "frameworks": FRAMEWORKS,
        "controls": controls,
        "certification_claim": False,
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _row_to_exception(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["compensating_controls"] = json_loads(item.pop("compensating_controls_json", "[]"), [])
    expiry = _parse_dt(item.get("expires_at"))
    item["expired"] = bool(expiry and expiry <= datetime.now(timezone.utc))
    item["active"] = item.get("status") == "approved" and not item["expired"]
    return item


def list_exceptions(workspace_id: str, *, include_expired: bool = True, limit: int = 200) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM compliance_exceptions WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(500, int(limit)))},
    )
    items = [_row_to_exception(row) for row in rows]
    return items if include_expired else [item for item in items if not item["expired"]]


def create_exception(
    actor_id: str,
    *,
    workspace_id: str,
    control_id: str,
    reason: str,
    compensating_controls: list[str] | None,
    expires_at: str,
    owner: str = "",
) -> dict[str, Any]:
    known = {item["id"] for item in _CONTROL_SPECS}
    if control_id not in known:
        raise ValueError("Contrôle réglementaire inconnu")
    expiry = _parse_dt(expires_at)
    if not expiry or expiry <= datetime.now(timezone.utc):
        raise ValueError("La date d'expiration doit être future")
    reason = reason.strip()
    if len(reason) < 10:
        raise ValueError("Une justification d'au moins 10 caractères est requise")
    exception_id = str(uuid.uuid4())
    now = utcnow()
    execute(
        """INSERT INTO compliance_exceptions(
            id,workspace_id,control_id,status,reason,compensating_controls_json,owner,expires_at,
            requested_by,reviewed_by,review_note,created_at,reviewed_at
        ) VALUES(:id,:ws,:control,'pending',:reason,:comp,:owner,:expires,:actor,NULL,NULL,:now,NULL)""",
        {
            "id": exception_id,
            "ws": workspace_id,
            "control": control_id,
            "reason": reason,
            "comp": json_dumps([str(x).strip() for x in (compensating_controls or []) if str(x).strip()]),
            "owner": owner.strip()[:180],
            "expires": expiry.isoformat(),
            "actor": actor_id,
            "now": now,
        },
    )
    record_event(
        "compliance.exception_requested",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="compliance_exception",
        resource_id=exception_id,
        payload={"control_id": control_id, "expires_at": expiry.isoformat()},
    )
    row = fetch_one("SELECT * FROM compliance_exceptions WHERE id=:id", {"id": exception_id})
    return _row_to_exception(row or {})


def decide_exception(actor_id: str, *, workspace_id: str, exception_id: str, decision: str, note: str = "") -> dict[str, Any]:
    decision = decision.strip().lower()
    if decision not in {"approved", "rejected", "revoked"}:
        raise ValueError("Décision d'exception invalide")
    row = fetch_one("SELECT * FROM compliance_exceptions WHERE id=:id AND workspace_id=:ws", {"id": exception_id, "ws": workspace_id})
    if not row:
        raise ValueError("Exception introuvable")
    current = _row_to_exception(row)
    if decision in {"approved", "rejected"} and current.get("status") != "pending":
        raise ValueError("Seule une exception en attente peut être approuvée ou rejetée")
    if decision == "revoked" and current.get("status") != "approved":
        raise ValueError("Seule une exception approuvée peut être révoquée")
    now = utcnow()
    execute(
        """UPDATE compliance_exceptions
           SET status=:status, reviewed_by=:actor, review_note=:note, reviewed_at=:now
           WHERE id=:id AND workspace_id=:ws""",
        {"status": decision, "actor": actor_id, "note": note.strip()[:2000], "now": now, "id": exception_id, "ws": workspace_id},
    )
    record_event(
        f"compliance.exception_{decision}",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="compliance_exception",
        resource_id=exception_id,
        payload={"control_id": current.get("control_id"), "decision": decision},
    )
    updated = fetch_one("SELECT * FROM compliance_exceptions WHERE id=:id", {"id": exception_id})
    return _row_to_exception(updated or {})


def posture(workspace_id: str, *, actor_id: str | None = None, framework_id: str | None = None, ensure_scan: bool = False) -> dict[str, Any]:
    scan = latest_compliance_scan(workspace_id)
    if scan is None and ensure_scan:
        if not actor_id:
            raise ValueError("Un actor_id est requis pour générer un scan")
        scan = run_compliance_scan(actor_id, workspace_id=workspace_id, source="regulatory_posture")
    scan = scan or {"status": "unknown", "controls": [], "scanned_at": None, "sha256": None}
    source = {str(item.get("id")): item for item in (scan.get("controls") or [])}
    exceptions = list_exceptions(workspace_id, include_expired=False)
    active_by_control = {item["control_id"]: item for item in exceptions if item.get("active")}
    catalog = control_catalog(framework_id)
    controls: list[dict[str, Any]] = []
    for spec in catalog["controls"]:
        observed = source.get(spec["source_control"], {})
        raw_status = str(observed.get("status") or "unknown")
        exception = active_by_control.get(spec["id"])
        effective = "excepted" if exception and raw_status == "fail" else raw_status
        controls.append({
            "id": spec["id"],
            "name": spec["name"],
            "category": spec["category"],
            "source_control": spec["source_control"],
            "status": raw_status,
            "effective_status": effective,
            "observed": observed.get("observed"),
            "desired": observed.get("desired"),
            "exception": {"id": exception["id"], "expires_at": exception["expires_at"], "owner": exception.get("owner", "")} if exception else None,
            "framework_mapping": spec["framework_mapping"],
        })
    total = len(controls)
    passed = sum(1 for item in controls if item["status"] == "pass")
    failed = sum(1 for item in controls if item["status"] == "fail")
    unknown = sum(1 for item in controls if item["status"] == "unknown")
    excepted = sum(1 for item in controls if item["effective_status"] == "excepted")
    result = {
        "product_version": PRODUCT_VERSION,
        "catalog_version": CATALOG_VERSION,
        "workspace_id": workspace_id,
        "framework_id": framework_id or "all",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_scan": {"id": scan.get("id"), "status": scan.get("status"), "scanned_at": scan.get("scanned_at"), "sha256": scan.get("sha256")},
        "summary": {
            "control_count": total,
            "pass": passed,
            "fail": failed,
            "unknown": unknown,
            "excepted": excepted,
            "compliant_percent": round((passed / total * 100) if total else 0.0, 1),
            "managed_percent": round(((passed + excepted) / total * 100) if total else 0.0, 1),
            "status": "pass" if total and failed == 0 and unknown == 0 else "warn" if total and failed == excepted else "fail" if failed else "unknown",
        },
        "controls": controls,
        "active_exception_count": len(active_by_control),
        "certification_claim": False,
    }
    result["sha256"] = _sha256_payload(result)
    return result


def capture_posture_snapshot(actor_id: str, *, workspace_id: str, framework_id: str | None = None) -> dict[str, Any]:
    item = posture(workspace_id, actor_id=actor_id, framework_id=framework_id, ensure_scan=True)
    snapshot_id = str(uuid.uuid4())
    item["id"] = snapshot_id
    execute(
        """INSERT INTO regulatory_posture_snapshots(id,workspace_id,framework_id,status,score,sha256,details_json,created_by,created_at)
           VALUES(:id,:ws,:framework,:status,:score,:sha,:details,:actor,:now)""",
        {
            "id": snapshot_id,
            "ws": workspace_id,
            "framework": framework_id or "all",
            "status": item["summary"]["status"],
            "score": item["summary"]["compliant_percent"],
            "sha": item["sha256"],
            "details": json_dumps(item),
            "actor": actor_id,
            "now": utcnow(),
        },
    )
    record_event(
        "compliance.posture_snapshot",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="regulatory_posture",
        resource_id=snapshot_id,
        payload={"framework_id": framework_id or "all", "score": item["summary"]["compliant_percent"], "sha256": item["sha256"]},
    )
    return item


def posture_history(workspace_id: str, *, framework_id: str | None = None, limit: int = 90) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ws": workspace_id, "limit": max(1, min(365, int(limit)))}
    if framework_id:
        rows = fetch_all(
            "SELECT * FROM regulatory_posture_snapshots WHERE workspace_id=:ws AND framework_id=:framework ORDER BY created_at DESC LIMIT :limit",
            {**params, "framework": framework_id},
        )
    else:
        rows = fetch_all("SELECT * FROM regulatory_posture_snapshots WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit", params)
    return [
        {
            "id": row.get("id"),
            "framework_id": row.get("framework_id"),
            "status": row.get("status"),
            "score": row.get("score"),
            "sha256": row.get("sha256"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def remediation_plan(workspace_id: str, *, framework_id: str | None = None) -> dict[str, Any]:
    current = posture(workspace_id, framework_id=framework_id)
    spec_by_id = {item["id"]: item for item in _CONTROL_SPECS}
    actions = []
    for control in current["controls"]:
        if control["status"] == "pass":
            continue
        spec = spec_by_id[control["id"]]
        priority = "high" if control["status"] == "fail" and not control.get("exception") else "medium" if control["status"] == "unknown" else "low"
        actions.append({
            "control_id": control["id"],
            "control_name": control["name"],
            "priority": priority,
            "status": control["effective_status"],
            "action": spec["remediation"],
            "verification": spec["verification"],
            "automation_mode": "proposal_only",
            "requires_human_approval": True,
            "exception_id": (control.get("exception") or {}).get("id"),
        })
    order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda item: (order.get(item["priority"], 9), item["control_id"]))
    return {
        "workspace_id": workspace_id,
        "framework_id": framework_id or "all",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action_count": len(actions),
        "actions": actions,
        "automatic_execution": False,
    }


def _csv_bytes(rows: list[dict[str, Any]], fields: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def create_regulatory_evidence_pack(actor_id: str, *, workspace_id: str, framework_id: str | None = None) -> dict[str, Any]:
    current = capture_posture_snapshot(actor_id, workspace_id=workspace_id, framework_id=framework_id)
    history = posture_history(workspace_id, framework_id=framework_id, limit=30)
    exceptions = list_exceptions(workspace_id, include_expired=True, limit=200)
    remediation = remediation_plan(workspace_id, framework_id=framework_id)
    catalog = control_catalog(framework_id)
    pack_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "format": "datavision-regulatory-evidence-v2",
        "product_version": PRODUCT_VERSION,
        "catalog_version": CATALOG_VERSION,
        "workspace_id": workspace_id,
        "framework_id": framework_id or "all",
        "created_at": created_at,
        "certification_claim": False,
        "files": ["catalog.json", "posture.json", "history.json", "exceptions.json", "remediation.json", "controls.csv"],
    }
    files: dict[str, bytes] = {
        "catalog.json": (json.dumps(catalog, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        "posture.json": (json.dumps(current, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        "history.json": (json.dumps(history, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        "exceptions.json": (json.dumps(exceptions, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        "remediation.json": (json.dumps(remediation, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        "controls.csv": _csv_bytes(current["controls"], ["id", "name", "category", "status", "effective_status", "observed", "desired"]),
    }
    manifest["sha256"] = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    files["manifest.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    root: Path = get_settings().data_root / "regulatory_evidence"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"regulatory-evidence-{pack_id}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    execute(
        """INSERT INTO regulatory_evidence_exports(id,workspace_id,framework_id,status,sha256,path,summary_json,created_by,created_at)
           VALUES(:id,:ws,:framework,:status,:sha,:path,:summary,:actor,:now)""",
        {
            "id": pack_id,
            "ws": workspace_id,
            "framework": framework_id or "all",
            "status": current["summary"]["status"],
            "sha": digest,
            "path": str(path),
            "summary": json_dumps({"score": current["summary"]["compliant_percent"], "exceptions": len(exceptions), "actions": remediation["action_count"]}),
            "actor": actor_id,
            "now": utcnow(),
        },
    )
    record_event(
        "compliance.regulatory_evidence_export",
        user_id=actor_id,
        workspace_id=workspace_id,
        resource_type="regulatory_evidence",
        resource_id=pack_id,
        payload={"framework_id": framework_id or "all", "sha256": digest, "status": current["summary"]["status"]},
    )
    return {
        "id": pack_id,
        "format": manifest["format"],
        "workspace_id": workspace_id,
        "framework_id": framework_id or "all",
        "path": str(path),
        "sha256": digest,
        "status": current["summary"]["status"],
        "score": current["summary"]["compliant_percent"],
        "created_at": created_at,
        "certification_claim": False,
    }


def list_regulatory_evidence_exports(workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT * FROM regulatory_evidence_exports WHERE workspace_id=:ws ORDER BY created_at DESC LIMIT :limit",
        {"ws": workspace_id, "limit": max(1, min(500, int(limit)))},
    )
    out = []
    for row in rows:
        item = dict(row)
        item["summary"] = json_loads(item.pop("summary_json", "{}"), {})
        out.append(item)
    return out


def get_regulatory_evidence_export(workspace_id: str, export_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM regulatory_evidence_exports WHERE id=:id AND workspace_id=:ws",
        {"id": export_id, "ws": workspace_id},
    )
    if not row:
        raise ValueError("Export de conformité introuvable")
    item = dict(row)
    item["summary"] = json_loads(item.pop("summary_json", "{}"), {})
    return item
