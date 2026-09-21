#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

EXPECTED_IDS = [
    "error_budget_alerting",
    "governed_sre_notifications",
    "s3_compatible_backups",
    "restore_drill",
    "queue_driven_autoscaling",
    "controlled_chaos",
    "sre_cockpit",
    "sre_ci_gate",
]


def inspect(root: Path) -> dict:
    errors: list[str] = []
    path = root / "compliance/SRE_ACCEPTANCE.json"
    if not path.is_file():
        return {"status": "fail", "errors": ["Missing compliance/SRE_ACCEPTANCE.json"]}
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if payload.get("product_version") != version:
        errors.append("manifest version mismatch")
    items = payload.get("items") or []
    if [item.get("id") for item in items] != EXPECTED_IDS:
        errors.append("SRE acceptance items mismatch")
    for item in items:
        for field in ("evidence", "tests"):
            values = item.get(field) or []
            if not values:
                errors.append(f"{item.get('id')}: no {field}")
            for rel in values:
                if not (root / rel).is_file():
                    errors.append(f"{item.get('id')}: missing {rel}")
    return {
        "product": payload.get("product"),
        "version": version,
        "items": len(items),
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }


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
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root / "backend")
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_sre_operations_v2600.py"],
            cwd=root / "backend",
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = done.stdout
        if done.returncode:
            result["status"] = "fail"
            result["errors"].append("Executable SRE tests failed")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"SRE acceptance: {result['status'].upper()} ({result.get('items', 0)}/8 items)")
        for error in result.get("errors", []):
            print("- " + error)
        if output:
            print(output.rstrip())
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
