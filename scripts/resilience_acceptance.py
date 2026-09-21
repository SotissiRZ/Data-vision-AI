#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, os, subprocess, sys
from pathlib import Path

EXPECTED_IDS = [
    "advanced_probes", "pod_disruption_budget", "horizontal_autoscaling", "schema_migrations",
    "verified_backup_restore", "scheduled_backups", "kms_online_rotation", "disaster_recovery_runbook",
]


def inspect(root: Path) -> dict:
    errors = []
    path = root / "compliance/RESILIENCE_ACCEPTANCE.json"
    if not path.is_file():
        return {"status": "fail", "errors": ["Missing compliance/RESILIENCE_ACCEPTANCE.json"]}
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if payload.get("product_version") != version: errors.append("manifest version mismatch")
    items = payload.get("items") or []
    if [item.get("id") for item in items] != EXPECTED_IDS: errors.append("Resilience acceptance items mismatch")
    for item in items:
        for field in ("evidence", "tests"):
            vals = item.get(field) or []
            if not vals: errors.append(f"{item.get('id')}: no {field}")
            for rel in vals:
                if not (root / rel).is_file(): errors.append(f"{item.get('id')}: missing {rel}")
    return {"product": payload.get("product"), "version": version, "items": len(items), "status": "pass" if not errors else "fail", "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = inspect(root)
    output = ""
    if args.check and result["status"] == "pass":
        env = dict(os.environ); env["PYTHONPATH"] = str(root / "backend")
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_resilience_ha_v2590.py"], cwd=root / "backend", env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = done.stdout
        if done.returncode:
            result["status"] = "fail"; result["errors"].append("Executable resilience tests failed")
    if args.json: print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Resilience acceptance: {result['status'].upper()} ({result.get('items', 0)}/8 items)")
        for error in result.get("errors", []): print("- " + error)
        if output: print(output.rstrip())
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
