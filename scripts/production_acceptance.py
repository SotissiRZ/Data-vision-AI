#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

CHECKS = [
    (
        "frontend_quality_gate",
        ".github/workflows/ci.yml",
        ["npm run typecheck", "npm run build", "frontend:"],
    ),
    (
        "compose_validation",
        ".github/workflows/ci.yml",
        ["compose-config:", "docker compose config -q"],
    ),
    (
        "helm_and_policy",
        ".github/workflows/ci.yml",
        ["helm lint", "helm template", "conftest"],
    ),
    (
        "deployed_e2e",
        ".github/workflows/ci.yml",
        ["e2e:", "test:e2e:smoke", "test:e2e:mvp", "test:e2e:production"],
    ),
    (
        "load_smoke",
        ".github/workflows/ci.yml",
        ["load_smoke.py", "production-load.json"],
    ),
    (
        "security_pipeline",
        ".github/workflows/security.yml",
        ["pip-audit", "npm audit", "trivy-action", "deployment-policy"],
    ),
    (
        "evidence_and_signoff",
        "scripts/production_signoff.py",
        ["REQUIRED_KINDS", "record", "verify", "production-signoff.json"],
    ),
    (
        "target_runner",
        "production-acceptance-windows.ps1",
        ["docker compose up", "test:e2e:production", "load_smoke.py", "production_signoff.py"],
    ),
]


def _version(root: Path) -> str:
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def run_checks(root: Path) -> list[dict]:
    results: list[dict] = []
    for check_id, rel, needles in CHECKS:
        path = root / rel
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        missing = [needle for needle in needles if needle not in text]
        results.append(
            {
                "id": check_id,
                "path": rel,
                "ok": path.is_file() and not missing,
                "missing": missing,
            }
        )
    return results


def write_manifest(root: Path, results: list[dict]) -> dict:
    passed = sum(1 for item in results if item["ok"])
    payload = {
        "product_version": _version(root),
        "acceptance": "conditional",
        "automation_ready": passed == len(results),
        "target_signoff": "pending",
        "passed": passed,
        "total": len(results),
        "checks": results,
        "p0_gaps": [
            {
                "section": 71,
                "title": "Critères d’acceptation",
                "status": "partial",
                "gap": "Les contrôles sont automatisés; leurs preuves doivent encore être exécutées et signées sur l’environnement cible.",
            },
            {
                "section": 74,
                "title": "Definition of Done",
                "status": "partial",
                "gap": "La DoD est exécutable et vérifiable; le sign-off CI/Docker/Helm/E2E/charge/sécurité/UAT reste une preuve externe à collecter.",
            },
        ],
        "required_target_evidence": [
            "ci",
            "compose",
            "helm",
            "e2e",
            "load",
            "security",
            "uat",
        ],
        "signoff_command": "python scripts/production_signoff.py verify --evidence-dir production-evidence --require-all",
    }
    (root / "compliance/PRODUCTION_ACCEPTANCE.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate DataVision production-acceptance automation.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    results = run_checks(root)
    payload = write_manifest(root, results)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"PRODUCTION_ACCEPTANCE: {payload['passed']}/{payload['total']}")
        for result in results:
            print(("PASS" if result["ok"] else "FAIL"), result["id"], "" if result["ok"] else result["missing"])
        if payload["automation_ready"]:
            print("Automation ready; target sign-off evidence is still required.")
    return 0 if payload["automation_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
