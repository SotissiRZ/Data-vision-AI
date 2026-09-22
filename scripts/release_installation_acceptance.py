#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

EXPECTED_IDS = [
    "version_freeze",
    "windows_version_alignment",
    "config_doctor",
    "upgrade_path",
    "stable_compose_state",
    "migration_marker",
    "release_workflow_complete",
    "reproducible_archive_contract",
]


def contains(path: Path, *needles: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def inspect(root: Path) -> dict:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    policy_path = root / "policies/release_candidate.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        policy = {}
    win_files = [root / name for name in ("install-windows.ps1", "preflight-windows.ps1", "rebuild-windows.ps1", "start-datavision.ps1", "upgrade-windows.ps1")]
    windows_ok = all(p.is_file() and "VERSION" in p.read_text(encoding="utf-8") and "v2.39.0" not in p.read_text(encoding="utf-8") for p in win_files)
    release_workflow = root / ".github/workflows/release.yml"
    checks = [
        ("version_freeze", version == "2.80.0" and policy.get("feature_freeze") is True and policy.get("stage") == "release_candidate"),
        ("windows_version_alignment", windows_ok),
        ("config_doctor", contains(root / "scripts/config_doctor.py", "production_secret_not_set", "compose_project_name_not_stable", "ANTIVIRUS_MODE")),
        ("upgrade_path", contains(root / "upgrade-windows.ps1", "--profile ops run --rm backup", "--profile ops run --rm migrate", "health/ready") and "down -v" not in (root / "upgrade-windows.ps1").read_text(encoding="utf-8")),
        ("stable_compose_state", contains(root / "docker-compose.yml", "name: datavision", "postgres_data:", "redis_data:", "clamav_data:")),
        ("migration_marker", contains(root / "backend/app/services/schema_migrations.py", 'version="2.80.0-001"', 'name="release_candidate_freeze_marker"')),
        ("release_workflow_complete", contains(release_workflow, "release_installation_acceptance.py", "quality_remediation_acceptance.py", "performance_slo_acceptance.py", "test:e2e:accessibility", "test:e2e:release-candidate", "scripts/verify_release.py")),
        ("reproducible_archive_contract", contains(root / "scripts/release.py", "FIXED_ZIP_TIME", "verify_archive") and contains(root / "scripts/verify_release.py", "_safe_member", "SHA256 invalide", "Archive corrompue")),
    ]
    rows = [{"id": cid, "ok": ok} for cid, ok in checks]
    return {
        "product": "DataVision AI",
        "product_version": version,
        "acceptance": "release_candidate_ready" if all(r["ok"] for r in rows) else "fail",
        "external_signoff": "pending",
        "passed": sum(1 for r in rows if r["ok"]),
        "total": len(rows),
        "checks": rows,
    }


def run_tests(root: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "backend")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_release_installation_v280.py"],
        cwd=root / "backend", env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate DataVision v2.80 Release Candidate installation/upgrade contract.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    result = inspect(root)
    output = ""
    if args.check and result["acceptance"] == "release_candidate_ready":
        code, output = run_tests(root)
        result["runtime_test"] = "pass" if code == 0 else "fail"
        if code:
            result["acceptance"] = "fail"
    (root / "compliance/RELEASE_INSTALLATION_ACCEPTANCE.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"RELEASE_INSTALLATION_ACCEPTANCE: {result['passed']}/{result['total']} ({result['acceptance']})")
        for row in result["checks"]:
            print(("PASS" if row["ok"] else "FAIL"), row["id"])
        if output:
            print(output.rstrip())
    return 0 if result["acceptance"] == "release_candidate_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
