#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def checks(root: Path):
    service = (root / "backend/app/services/performance_evidence.py").read_text(encoding="utf-8")
    routes = (root / "backend/app/api/routes/enterprise.py").read_text(encoding="utf-8")
    metadata = (root / "backend/app/services/metadata_store.py").read_text(encoding="utf-8")
    migrations = (root / "backend/app/services/schema_migrations.py").read_text(encoding="utf-8")
    frontend = (root / "frontend/app/page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/lib/api.ts").read_text(encoding="utf-8")
    policy_path = root / "policies/performance_slo.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    runner = (root / "scripts/performance_benchmark.py").read_text(encoding="utf-8")
    test = "backend/tests/test_performance_slo_v277.py"
    doc = "docs/PERFORMANCE_SLO_EVIDENCE_V2770.md"
    return [
        ("versioned performance slo policy", policy.get("schema") == "datavision.performance-slo-policy/v1" and "production_standard" in policy.get("profiles", {}), ["policies/performance_slo.json"], [test]),
        ("workspace evidence ledger and migration", "performance_evidence_runs" in metadata and "2.77.0-001" in migrations, ["backend/app/services/metadata_store.py", "backend/app/services/schema_migrations.py"], [test]),
        ("local benchmark separated from production evidence", "production_evidence" in service and "ne constitue pas une mesure de capacité production" in service, ["backend/app/services/performance_evidence.py"], [test]),
        ("external target load runner", "ThreadPoolExecutor" in runner and "request_p95_ms" in runner and "artifact_sha256" in runner, ["scripts/performance_benchmark.py"], [test]),
        ("governed evidence validation", "validate_external_evidence" in service and "source_artifact_sha256" in service and "_is_nonlocal_https_target" in service, ["backend/app/services/performance_evidence.py"], [test]),
        ("enterprise performance api", "/operational/performance" in routes and "run_local_benchmark" in routes and "import_external_evidence" in routes, ["backend/app/api/routes/enterprise.py"], [test]),
        ("operational intelligence cockpit", "Performance & SLO Evidence" in frontend and "getPerformanceEvidence" in api and "runLocalPerformanceBenchmark" in api, ["frontend/app/page.tsx", "frontend/lib/api.ts"], [test]),
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
        "note": "Internal engineering acceptance. Production SLO compliance requires measured external-target evidence; local smoke runs are deliberately non-production evidence.",
    }
    (root / "compliance/PERFORMANCE_SLO_ACCEPTANCE.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for item in items:
        print(f"{'PASS' if item['ok'] else 'FAIL'} · {item['id']}")
    print(f"PERFORMANCE_SLO_ACCEPTANCE {payload['passed']}/{payload['total']}")
    if args.check and payload["passed"] != payload["total"]:
        return 2
    if args.check:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "backend/tests/test_performance_slo_v277.py"], cwd=root, env={**os.environ, "PYTHONPATH": str(root / "backend")})
        return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
