from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = ROOT / "compliance" / "CDC_COVERAGE_MATRIX.json"
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

    mvp_items = [
        {"name": "auth", "evidence": ["backend/app/services/auth_service.py"]},
        {"name": "workspace", "evidence": ["backend/app/services/workspace_service.py"]},
        {"name": "upload_csv_xlsx_json_parquet", "evidence": ["backend/app/services/storage.py"]},
        {"name": "profiling", "evidence": ["backend/app/services/profiling.py"]},
        {"name": "quality", "evidence": ["backend/app/services/quality.py"]},
        {"name": "preparation", "evidence": ["backend/app/services/preparation.py"]},
        {"name": "statistics", "evidence": ["backend/app/services/statistics_engine.py"]},
        {"name": "visualization", "evidence": ["backend/app/services/visualization.py"]},
        {"name": "local_sql", "evidence": ["backend/app/services/data_workspace.py"]},
        {"name": "ai_analyst", "evidence": ["backend/app/services/ai_analyst.py"]},
        {"name": "nlq", "evidence": ["backend/app/services/nlq_sql.py"]},
        {"name": "insights", "evidence": ["backend/app/services/proactive_intelligence.py"]},
        {"name": "pdf_html_export", "evidence": ["backend/app/services/report_builder.py"]},
        {"name": "history", "evidence": ["backend/app/services/analysis_history.py"]},
        {"name": "docker", "evidence": ["docker-compose.yml"]},
        {"name": "tests", "evidence": ["backend/tests"]},
    ]
    for item in mvp_items:
        item["pass"] = all((ROOT / value).exists() for value in item["evidence"])
    mvp_pass = all(item["pass"] for item in mvp_items)

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
