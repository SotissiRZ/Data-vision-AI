#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

CHECKS = [
    ("persistent_python_kernel", "sandbox/app/kernel_worker.py", ["execution_count", "namespace", "_exec_last_expr"]),
    ("persistent_r_kernel", "sandbox/app/r_kernel_worker.R", ["execution_count", ".GlobalEnv", "repeat"]),
    ("kernel_session_manager", "sandbox/app/kernel_manager.py", ["KernelManager", "restart", "SESSION_TTL_SECONDS"]),
    ("backend_session_contract", "backend/app/services/notebook_sandbox.py", ["execute_sandboxed_session", "open_kernel_session", "restart_kernel_session"]),
    ("environment_locking", "backend/app/services/notebook_service.py", ["notebook_environments", "sync_notebook_environment", "python_lock_json"]),
    ("kernel_api", "backend/app/api/routes/notebooks.py", ["/kernels", "/environment/sync", "KernelRestartAllRequest"]),
    ("notebook_runtime_ui", "frontend/components/NotebookStudio.tsx", ["Runtime persistant", "Redémarrer + reconstruire", "Environnement & packages"]),
    ("persistent_runtime_tests", "backend/tests/test_notebook_persistent_v267.py", ["preserves_namespace", "same_persistent_session", "environment_lock"]),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    results = []
    for check_id, rel, needles in CHECKS:
        path = root / rel
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        missing = [needle for needle in needles if needle not in text]
        results.append({"id": check_id, "ok": path.exists() and not missing, "missing": missing, "path": rel})
    passed = sum(1 for item in results if item["ok"])
    payload = {
        "product_version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "passed": passed,
        "total": len(results),
        "checks": results,
    }
    (root / "compliance/NOTEBOOK_RUNTIME_ACCEPTANCE.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"NOTEBOOK_RUNTIME_ACCEPTANCE: {passed}/{len(results)}")
    for item in results:
        print(("PASS" if item["ok"] else "FAIL"), item["id"], "" if item["ok"] else item["missing"])
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
