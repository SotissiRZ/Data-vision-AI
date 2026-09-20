#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

EXPECTED_STAGES = [
    "import",
    "profiling",
    "quality",
    "preparation",
    "statistics",
    "visualization",
    "history",
    "export",
]


def inspect(root: Path) -> dict:
    errors: list[str] = []
    manifest_path = root / "compliance" / "MVP_ACCEPTANCE.json"
    if not manifest_path.is_file():
        return {"status": "fail", "errors": ["Missing compliance/MVP_ACCEPTANCE.json"]}

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "fail", "errors": [f"Invalid MVP_ACCEPTANCE.json: {exc}"]}

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if payload.get("product_version") != version:
        errors.append(
            f"MVP manifest version={payload.get('product_version')!r}, VERSION={version!r}"
        )

    items = payload.get("items") or []
    if payload.get("mandatory_count") != 16 or len(items) != 16:
        errors.append("MVP acceptance must declare exactly 16 mandatory items")
    ids = [item.get("id") for item in items]
    if ids != list(range(1, 17)):
        errors.append("MVP item ids must be exactly 1..16 in order")

    for item in items:
        name = item.get("name") or f"item-{item.get('id')}"
        evidence = item.get("evidence") or []
        tests = item.get("tests") or []
        if not evidence:
            errors.append(f"{name}: no evidence declared")
        if not tests:
            errors.append(f"{name}: no tests declared")
        for rel in [*evidence, *tests]:
            if not (root / rel).exists():
                errors.append(f"{name}: missing {rel}")

    workflow = payload.get("workflow_gate") or {}
    if workflow.get("stages") != EXPECTED_STAGES:
        errors.append("MVP core workflow stages do not match the v2.41 acceptance contract")
    for key in ("integration_test", "deployed_test"):
        rel = workflow.get(key)
        if not rel or not (root / rel).is_file():
            errors.append(f"MVP workflow missing {key}: {rel!r}")

    return {
        "product": payload.get("product"),
        "version": version,
        "mandatory_items": len(items),
        "workflow_stages": workflow.get("stages") or [],
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }


def run_runtime_test(root: Path) -> tuple[int, str]:
    test_path = root / "backend" / "tests" / "test_mvp_workflow_v241.py"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        str(test_path),
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
    parser = argparse.ArgumentParser(description="Validate the 16-item DataVision MVP acceptance gate.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true", help="Run the executable backend MVP workflow test.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    result = inspect(root)
    runtime_output = ""
    if args.check and result["status"] == "pass":
        code, runtime_output = run_runtime_test(root)
        result["runtime_test"] = "pass" if code == 0 else "fail"
        if code != 0:
            result["status"] = "fail"
            result["errors"].append("Executable MVP workflow test failed")
    elif args.check:
        result["runtime_test"] = "not_run"

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if runtime_output:
            print(runtime_output.rstrip())
    else:
        print(
            f"MVP acceptance: {result['status'].upper()} "
            f"({result.get('mandatory_items', 0)}/16 items, "
            f"{len(result.get('workflow_stages', []))}/8 core stages)"
        )
        for error in result.get("errors", []):
            print(f"- {error}")
        if runtime_output:
            print(runtime_output.rstrip())
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
