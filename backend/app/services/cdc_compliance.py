from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _resolve_project_root() -> Path:
    """Resolve the DataVision project root in source and packaged Docker layouts.

    Source tree: <repo>/backend/app/services/...
    Docker image: /app/app/services/... with compliance copied to /app/compliance.
    """
    candidates: list[Path] = []
    configured = os.getenv("DATAVISION_PROJECT_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend([
        Path("/app"),
        Path(__file__).resolve().parents[3],
        Path.cwd(),
    ])
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if (resolved / "compliance" / "CDC_COVERAGE_MATRIX.json").is_file():
            return resolved
    # Keep a deterministic fallback so callers receive a precise FileNotFoundError.
    return Path("/app") if Path("/app").exists() else Path(__file__).resolve().parents[3]


ROOT = _resolve_project_root()
MATRIX_PATH = ROOT / "compliance" / "CDC_COVERAGE_MATRIX.json"
MVP_PATH = ROOT / "compliance" / "MVP_ACCEPTANCE.json"
WEIGHTS = {"implemented": 1.0, "partial": 0.5, "missing": 0.0}


def _load() -> dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _evidence_state(item: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    for value in item.get("evidence") or []:
        path = ROOT / value
        evidence.append({"path": value, "exists": path.exists()})
    tests = []
    for value in item.get("tests") or []:
        path = ROOT / value
        tests.append({"path": value, "exists": path.exists()})
    return {
        "evidence": evidence,
        "tests": tests,
        "evidence_ok": all(row["exists"] for row in evidence + tests),
    }


def get_cdc_report() -> dict[str, Any]:
    payload = _load()
    rows = []
    for item in payload["requirements"]:
        state = _evidence_state(item)
        row = {**item, **state}
        rows.append(row)

    total = len(rows)
    weighted = sum(WEIGHTS.get(row["status"], 0.0) for row in rows)
    counts = {
        key: sum(1 for row in rows if row["status"] == key)
        for key in WEIGHTS
    }
    priority_gaps = {
        priority: [
            {
                "section": row["section"],
                "title": row["title"],
                "status": row["status"],
                "gaps": row.get("gaps") or [],
            }
            for row in rows
            if row["priority"] == priority and row["status"] != "implemented"
        ]
        for priority in ("P0", "P1", "P2")
    }
    missing_evidence = [
        {
            "section": row["section"],
            "title": row["title"],
            "missing": [
                item["path"]
                for item in row["evidence"] + row["tests"]
                if not item["exists"]
            ],
        }
        for row in rows
        if not row["evidence_ok"]
    ]

    mvp_payload = json.loads(MVP_PATH.read_text(encoding="utf-8"))
    mvp_items = []
    for declared in mvp_payload.get("items") or []:
        evidence = list(declared.get("evidence") or [])
        tests = list(declared.get("tests") or [])
        missing = [value for value in [*evidence, *tests] if not (ROOT / value).exists()]
        mvp_items.append({
            "id": declared.get("id"),
            "name": declared.get("name"),
            "evidence": evidence,
            "tests": tests,
            "missing": missing,
            "pass": bool(evidence) and bool(tests) and not missing,
        })
    workflow = mvp_payload.get("workflow_gate") or {}
    workflow_paths = [workflow.get("integration_test"), workflow.get("deployed_test")]
    workflow_missing = [value for value in workflow_paths if not value or not (ROOT / value).is_file()]
    mvp_manifest_ok = (
        mvp_payload.get("product_version") == payload.get("product_version")
        and mvp_payload.get("mandatory_count") == 16
        and len(mvp_items) == 16
        and not workflow_missing
    )
    mvp_pass = mvp_manifest_ok and all(item["pass"] for item in mvp_items)

    blockers = priority_gaps["P0"]
    overall = "accepted" if not blockers and counts["partial"] == 0 and counts["missing"] == 0 else (
        "conditional" if counts["missing"] == 0 else "not_accepted"
    )

    return {
        "cdc_version": payload["cdc_version"],
        "product_version": payload["product_version"],
        "summary": {
            "sections": total,
            "implemented": counts["implemented"],
            "partial": counts["partial"],
            "missing": counts["missing"],
            "weighted_coverage_percent": round(weighted / max(total, 1) * 100.0, 1),
            "evidence_complete": not missing_evidence,
            "mvp_acceptance": "pass" if mvp_pass else "conditional",
            "overall_acceptance": overall,
            "mvp_items": mvp_items,
            "mvp_workflow": {
                "name": workflow.get("name"),
                "stages": workflow.get("stages") or [],
                "integration_test": workflow.get("integration_test"),
                "deployed_test": workflow.get("deployed_test"),
                "missing": workflow_missing,
                "pass": mvp_manifest_ok and not workflow_missing,
            },
        },
        "priority_gaps": priority_gaps,
        "missing_evidence": missing_evidence,
        "requirements": rows,
        "methodology": {
            "implemented": "1.0 point — fonctionnalité présente avec preuve code/documentation.",
            "partial": "0.5 point — fondation réelle mais exigence CDC non totalement couverte.",
            "missing": "0 point — exigence non implémentée.",
            "note": "Le score mesure la couverture du CDC, pas la qualité scientifique intrinsèque ni la réussite d'un déploiement production externe.",
        },
    }


def production_acceptance() -> dict[str, Any]:
    report = get_cdc_report()
    summary = report["summary"]
    gates = [
        {
            "id": "mvp",
            "label": "MVP obligatoire",
            "status": summary["mvp_acceptance"],
            "blocking": summary["mvp_acceptance"] != "pass",
        },
        {
            "id": "evidence",
            "label": "Preuves code/tests présentes",
            "status": "pass" if summary["evidence_complete"] else "fail",
            "blocking": not summary["evidence_complete"],
        },
        {
            "id": "security",
            "label": "Security CDC complet",
            "status": "conditional" if report["priority_gaps"]["P0"] else "pass",
            "blocking": bool(report["priority_gaps"]["P0"]),
        },
        {
            "id": "full_cdc",
            "label": "CDC 100%",
            "status": "pass" if summary["partial"] == 0 and summary["missing"] == 0 else "conditional",
            "blocking": False,
        },
    ]
    return {
        "product_version": report["product_version"],
        "acceptance": summary["overall_acceptance"],
        "coverage_percent": summary["weighted_coverage_percent"],
        "gates": gates,
        "p0_gaps": report["priority_gaps"]["P0"],
        "signoff_required": [
            "Exécution réelle du pipeline GitHub Actions sur le dépôt cible.",
            "Validation Docker/Compose dans l'environnement de déploiement.",
            "Tests de charge/SLO sur infrastructure cible.",
            "Revue sécurité des gaps MFA/WebAuthn et antivirus d'upload.",
            "Acceptance utilisateur métier sur les workflows prioritaires.",
        ],
    }
