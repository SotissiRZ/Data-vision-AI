#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

EXPECTED_IDS = [
    "sql_workspace",
    "python_sandbox",
    "r_sandbox",
    "version_binding",
    "run_all",
    "artifacts",
    "artifact_promotion",
    "provenance",
]


def inspect(root: Path) -> dict:
    errors: list[str] = []
    path = root / "compliance" / "WORKSPACE_ACCEPTANCE.json"
    if not path.is_file():
        return {"status": "fail", "errors": ["Missing compliance/WORKSPACE_ACCEPTANCE.json"]}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "fail", "errors": [f"Invalid WORKSPACE_ACCEPTANCE.json: {exc}"]}
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if payload.get("product_version") != version:
        errors.append(f"Workspace manifest version={payload.get('product_version')!r}, VERSION={version!r}")
    items = payload.get("items") or []
    ids = [item.get("id") for item in items]
    if ids != EXPECTED_IDS:
        errors.append("Workspace acceptance items do not match the v2.43 contract")
    for item in items:
        name = item.get("name") or item.get("id")
        for field in ("evidence", "tests"):
            values = item.get(field) or []
            if not values:
                errors.append(f"{name}: no {field} declared")
            for rel in values:
                if not (root / rel).is_file():
                    errors.append(f"{name}: missing {rel}")
    return {
        "product": payload.get("product"),
        "version": version,
        "items": len(items),
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }


def run_runtime_tests(root: Path) -> tuple[int, str]:
    command = [
        sys.executable, "-m", "pytest", "-q",
        "tests/test_notebook_v218.py",
        "tests/test_data_workspace_v243.py",
        "tests/test_frontend_workspace_v243.py",
    ]
    completed = subprocess.run(
        command,
        cwd=root / "backend",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.returncode, completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DataVision v2.43 Data Workspace completion.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = inspect(root)
    output = ""
    if args.check and result["status"] == "pass":
        code, output = run_runtime_tests(root)
        result["runtime_test"] = "pass" if code == 0 else "fail"
        if code:
            result["status"] = "fail"
            result["errors"].append("Executable workspace acceptance tests failed")
    elif args.check:
        result["runtime_test"] = "not_run"
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Workspace acceptance: {result['status'].upper()} ({result.get('items', 0)}/8 items)")
        for error in result.get("errors", []):
            print(f"- {error}")
        if output:
            print(output.rstrip())
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
