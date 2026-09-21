#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

EXPECTED_IDS = [
    "platform_wide_scope",
    "minimum_text_floor",
    "readable_default_scale",
    "reading_modes",
    "controls_readability",
    "data_density_readability",
    "assistant_readability",
    "responsive_readability",
]


def inspect(root: Path) -> dict:
    errors = []
    path = root / "compliance/TYPOGRAPHY_ACCEPTANCE.json"
    if not path.is_file():
        return {"status": "fail", "errors": ["Missing compliance/TYPOGRAPHY_ACCEPTANCE.json"]}
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if payload.get("product_version") != version:
        errors.append(f"manifest version={payload.get('product_version')!r}, VERSION={version!r}")
    items = payload.get("items") or []
    if [x.get("id") for x in items] != EXPECTED_IDS:
        errors.append("Typography acceptance items do not match v2.53.3 contract")
    for item in items:
        for field in ("evidence", "tests"):
            vals = item.get(field) or []
            if not vals:
                errors.append(f"{item.get('id')}: no {field}")
            for rel in vals:
                if not (root / rel).is_file():
                    errors.append(f"{item.get('id')}: missing {rel}")
    return {
        "product": payload.get("product"),
        "version": version,
        "items": len(items),
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }


def run_tests(root: Path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "backend")
    command = [sys.executable, "-m", "pytest", "-q", "tests/test_frontend_typography_v2533.py"]
    completed = subprocess.run(
        command,
        cwd=root / "backend",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.returncode, completed.stdout


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
        code, output = run_tests(root)
        result["runtime_test"] = "pass" if code == 0 else "fail"
        if code:
            result["status"] = "fail"
            result["errors"].append("Executable typography tests failed")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Typography acceptance: {result['status'].upper()} ({result.get('items', 0)}/8 items)")
        for error in result.get("errors", []):
            print("- " + error)
        if output:
            print(output.rstrip())
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
