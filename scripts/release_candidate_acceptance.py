#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

EXPECTED_IDS = [
    "security_headers",
    "strict_signoff_integrity",
    "ordered_idempotent_migrations",
    "backup_restore_drill",
    "full_gate_ci",
    "release_candidate_e2e",
    "external_boundary_preserved",
    "versioned_release_evidence",
]


def _contains(path: Path, *needles: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def inspect(root: Path) -> dict:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    ci = root / ".github/workflows/ci.yml"
    signoff = root / "scripts/production_signoff.py"
    migrations = root / "backend/app/services/schema_migrations.py"
    main = root / "backend/app/main.py"
    next_config = root / "frontend/next.config.mjs"
    e2e = root / "frontend/e2e/release-candidate.spec.ts"
    prod = root / "compliance/PRODUCTION_ACCEPTANCE.json"
    checks = [
        ("security_headers", _contains(main, "X-Content-Type-Options", "Strict-Transport-Security") and _contains(next_config, "X-Content-Type-Options", "Strict-Transport-Security")),
        ("strict_signoff_integrity", _contains(signoff, "evidence_sha256", "attachment sha256 mismatch", "--allow-waivers", "strict")),
        ("ordered_idempotent_migrations", _contains(migrations, "ordered_migrations", "2.81.0-001", "security_documentation_freeze", "release_candidate_hardening_marker")),
        ("backup_restore_drill", _contains(root / "backend/app/services/backup_service.py", "run_restore_drill", "_verify_manifest_files", "_safe_extract")),
        ("full_gate_ci", _contains(ci, "quality_remediation_acceptance.py", "storytelling_acceptance.py", "model_gateway_acceptance.py", "i18n_accessibility_acceptance.py", "cloud_cdc_acceptance.py", "workspace_environment_acceptance.py", "performance_slo_acceptance.py", "cdc_gap_closure_acceptance.py", "release_candidate_acceptance.py", "release_installation_acceptance.py")),
        ("release_candidate_e2e", _contains(e2e, "@release-candidate", "x-request-id", "security headers") and _contains(root / "frontend/package.json", "test:e2e:release-candidate")),
        ("external_boundary_preserved", _contains(prod, '"acceptance": "conditional"', '"target_signoff": "pending"') and _contains(root / "docs/compliance/UAT_SIGNOFF_TEMPLATE.md", "UAT")),
        ("versioned_release_evidence", version == "2.81.0" and _contains(root / "scripts/production_baseline.py", 'EXPECTED_VERSION = "2.81.0"')),
    ]
    rows = [{"id": check_id, "ok": ok} for check_id, ok in checks]
    return {
        "product": "DataVision AI",
        "product_version": version,
        "acceptance": "technical_ready" if all(row["ok"] for row in rows) else "fail",
        "external_signoff": "pending",
        "passed": sum(1 for row in rows if row["ok"]),
        "total": len(rows),
        "checks": rows,
    }


def run_tests(root: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "backend")
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_release_candidate_hardening_v279.py"],
        cwd=root / "backend",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return done.returncode, done.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate DataVision release-candidate hardening on v2.81 security/documentation freeze.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    result = inspect(root)
    output = ""
    if args.check and result["acceptance"] == "technical_ready":
        code, output = run_tests(root)
        result["runtime_test"] = "pass" if code == 0 else "fail"
        if code:
            result["acceptance"] = "fail"
    (root / "compliance/RELEASE_CANDIDATE_ACCEPTANCE.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"RELEASE_CANDIDATE_ACCEPTANCE: {result['passed']}/{result['total']} ({result['acceptance']})")
        for row in result["checks"]:
            print(("PASS" if row["ok"] else "FAIL"), row["id"])
        if output:
            print(output.rstrip())
    return 0 if result["acceptance"] == "technical_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
