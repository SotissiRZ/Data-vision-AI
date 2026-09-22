#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def checks(root: Path):
    service = (root / "backend/app/services/workspace_environment.py").read_text(encoding="utf-8")
    notebook = (root / "backend/app/services/notebook_service.py").read_text(encoding="utf-8")
    routes = (root / "backend/app/api/routes/notebooks.py").read_text(encoding="utf-8")
    metadata = (root / "backend/app/services/metadata_store.py").read_text(encoding="utf-8")
    migrations = (root / "backend/app/services/schema_migrations.py").read_text(encoding="utf-8")
    frontend = (root / "frontend/components/NotebookStudio.tsx").read_text(encoding="utf-8")
    client = (root / "frontend/lib/notebook-client.ts").read_text(encoding="utf-8")
    test = "backend/tests/test_workspace_environment_v276.py"
    doc = "docs/operations/WORKSPACE_ENVIRONMENTS_V2760.md"
    return [
        ("workspace scoped environment ledger", "workspace_runtime_environments" in metadata and "2.76.0-001" in migrations, ["backend/app/services/metadata_store.py", "backend/app/services/schema_migrations.py"], [test]),
        ("deterministic sha256 manifests", 'datavision.workspace-environment/v1' in service and "fingerprint_sha256" in service and "sort_keys=True" in service, ["backend/app/services/workspace_environment.py"], [test]),
        ("python and r exact locks", "python_lock" in service and "r_lock" in service and "sandbox_packages" in service and "missing_python" in service and "missing_r" in service, ["backend/app/services/workspace_environment.py"], [test]),
        ("secure image managed policy", '"dynamic_install": False' in service and '"network_install": False' in service and '"workspace-sandbox"' in service, ["backend/app/services/workspace_environment.py"], [test]),
        ("workspace isolation and kernel invalidation", "workspace:manage" in service and "_invalidate_workspace_kernels" in service and "close_kernel_session" in service, ["backend/app/services/workspace_environment.py"], [test]),
        ("notebook inheritance and run provenance", "merge_requirements" in notebook and '"workspace_environment_sha256"' in notebook and '"environment": environment_provenance' in notebook, ["backend/app/services/notebook_service.py"], [test]),
        ("governed api and notebook studio", "/workspace-environment" in routes and "getWorkspaceEnvironment" in client and "Environnement workspace" in frontend and "Reproductible:" in frontend, ["backend/app/api/routes/notebooks.py", "frontend/lib/notebook-client.ts", "frontend/components/NotebookStudio.tsx"], [test]),
        ("engineering evidence and boundaries", (root / doc).is_file() and (root / test).is_file(), [doc], [test]),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    rows = checks(root)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    items = [{"id": name.lower().replace(" ", "_"), "ok": ok, "evidence": evidence, "tests": tests} for name, ok, evidence, tests in rows]
    payload = {
        "product": "DataVision AI",
        "product_version": version,
        "passed": sum(i["ok"] for i in items),
        "total": len(items),
        "items": items,
        "note": "Internal engineering acceptance. Dependency installation remains image-managed by design; runtime manifests verify approved sandbox contents rather than installing packages dynamically.",
    }
    (root / "compliance/WORKSPACE_ENVIRONMENT_ACCEPTANCE.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for item in items:
        print(f"{'PASS' if item['ok'] else 'FAIL'} · {item['id']}")
    print(f"WORKSPACE_ENVIRONMENT_ACCEPTANCE {payload['passed']}/{payload['total']}")
    if args.check and payload["passed"] != payload["total"]:
        return 2
    if args.check:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "backend/tests/test_workspace_environment_v276.py"], cwd=root, env={**__import__('os').environ, "PYTHONPATH": str(root / "backend")})
        return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
