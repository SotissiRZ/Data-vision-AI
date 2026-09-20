#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_VERSION = "2.53.0"
EXPECTED_CRYPTOGRAPHY = "cryptography==46.0.5"
REQUIRED_FILES = (
    "VERSION",
    "backend/requirements.txt",
    "backend/Dockerfile",
    "docker-compose.yml",
    "compliance/CDC_COVERAGE_MATRIX.json",
    "compliance/PRODUCTION_ACCEPTANCE.json",
    "compliance/MVP_ACCEPTANCE.json",
    "compliance/PREPARATION_ACCEPTANCE.json",
    "compliance/WORKSPACE_ACCEPTANCE.json",
    "compliance/ASSISTANT_ACCEPTANCE.json",
    "compliance/ASSISTANT_MULTIMODAL_ACCEPTANCE.json",
    "compliance/MULTI_AGENT_ACCEPTANCE.json",
    "compliance/SEMANTIC_ACCEPTANCE.json",
    "compliance/INSIGHT_ACCEPTANCE.json",
    "compliance/REPORT_ACCEPTANCE.json",
    "compliance/AUTOML_ACCEPTANCE.json",
    "compliance/ML_SAFETY_ACCEPTANCE.json",
    "compliance/XAI_ACCEPTANCE.json",
    "compliance/FORECASTING_ANOMALY_ACCEPTANCE.json",
    "frontend/package.json",
    "frontend/next.config.mjs",
    "frontend/lib/assistant/orchestrator-adapter.ts",
    "scripts/repository_hygiene.py",
    "scripts/mvp_acceptance.py",
    "scripts/preparation_acceptance.py",
    "scripts/workspace_acceptance.py",
    "scripts/assistant_acceptance.py",
    "scripts/assistant_multimodal_acceptance.py",
    "scripts/multi_agent_acceptance.py",
    "scripts/semantic_acceptance.py",
    "scripts/insight_acceptance.py",
    "scripts/report_acceptance.py",
    "scripts/automl_acceptance.py",
    "scripts/ml_safety_acceptance.py",
    "scripts/xai_acceptance.py",
    "scripts/forecasting_anomaly_acceptance.py",
    "scripts/verify_release.py",
    "backend/tests/test_mvp_workflow_v241.py",
    "backend/tests/test_data_preparation_v242.py",
    "backend/tests/test_pipelines_v242.py",
    "backend/tests/test_frontend_preparation_v242.py",
    "backend/tests/test_data_workspace_v243.py",
    "backend/tests/test_frontend_workspace_v243.py",
    "backend/tests/assistant/test_assistant_v244.py",
    "backend/tests/test_frontend_assistant_v244.py",
    "backend/tests/assistant/test_assistant_v245.py",
    "backend/tests/test_frontend_assistant_v245.py",
    "backend/tests/assistant/test_multi_agent_v246.py",
    "backend/tests/test_frontend_assistant_v246.py",
    "backend/tests/test_semantic_nlq_v247.py",
    "backend/tests/test_frontend_semantic_v247.py",
    "backend/tests/test_insight_engine_v248.py",
    "backend/tests/test_frontend_insights_v248.py",
    "backend/tests/test_reporting_v249.py",
    "backend/tests/test_frontend_reporting_v249.py",
    "backend/tests/test_automl_v2500.py",
    "backend/tests/test_frontend_automl_v2500.py",
    "backend/tests/test_ml_safety_v2510.py",
    "backend/tests/test_xai_v2520.py",
    "backend/tests/test_forecasting_anomaly_v2530.py",
    "backend/app/services/ml_guardrails.py",
    "backend/app/services/insight_engine.py",
    "backend/app/assistant/agents.py",
    "frontend/lib/assistant/effects.ts",
    "frontend/e2e/mvp.spec.ts",
)


def check(root: Path) -> list[str]:
    errors: list[str] = []

    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            errors.append(f"Missing required file: {rel}")

    version_path = root / "VERSION"
    if version_path.is_file():
        version = version_path.read_text(encoding="utf-8").strip()
        if version != EXPECTED_VERSION:
            errors.append(f"VERSION={version!r}, expected {EXPECTED_VERSION!r}")

    req_path = root / "backend/requirements.txt"
    if req_path.is_file():
        requirements = {
            line.strip()
            for line in req_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        if EXPECTED_CRYPTOGRAPHY not in requirements:
            errors.append(f"Missing required dependency pin: {EXPECTED_CRYPTOGRAPHY}")
        if "cryptography==46.0.4" in requirements:
            errors.append("Forbidden stale dependency pin: cryptography==46.0.4")
        if "snowflake-connector-python==4.7.4" not in requirements:
            errors.append("Unexpected Snowflake connector pin")

    compose_path = root / "docker-compose.yml"
    if compose_path.is_file():
        compose = compose_path.read_text(encoding="utf-8")
        if "NEXT_PUBLIC_API_URL: /api/backend" not in compose:
            errors.append("Same-origin frontend API proxy is not configured in docker-compose.yml")

    backend_dockerfile = root / "backend/Dockerfile"
    if backend_dockerfile.is_file():
        dockerfile = backend_dockerfile.read_text(encoding="utf-8")
        if "COPY compliance ./compliance" not in dockerfile:
            errors.append("backend/Dockerfile does not copy compliance/")

    package_path = root / "frontend/package.json"
    if package_path.is_file():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid frontend/package.json: {exc}")
        else:
            scripts = package.get("scripts", {})
            for script in ("build", "typecheck", "test:e2e:smoke", "test:e2e:mvp"):
                if not scripts.get(script):
                    errors.append(f"Missing frontend npm script: {script}")

    for rel in ("compliance/CDC_COVERAGE_MATRIX.json", "compliance/PRODUCTION_ACCEPTANCE.json", "compliance/MVP_ACCEPTANCE.json", "compliance/PREPARATION_ACCEPTANCE.json", "compliance/WORKSPACE_ACCEPTANCE.json", "compliance/ASSISTANT_ACCEPTANCE.json", "compliance/ASSISTANT_MULTIMODAL_ACCEPTANCE.json", "compliance/MULTI_AGENT_ACCEPTANCE.json", "compliance/SEMANTIC_ACCEPTANCE.json", "compliance/INSIGHT_ACCEPTANCE.json", "compliance/REPORT_ACCEPTANCE.json", "compliance/AUTOML_ACCEPTANCE.json", "compliance/ML_SAFETY_ACCEPTANCE.json", "compliance/XAI_ACCEPTANCE.json", "compliance/FORECASTING_ANOMALY_ACCEPTANCE.json"):
        path = root / rel
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in {rel}: {exc}")
            continue
        if payload.get("product_version") != EXPECTED_VERSION:
            errors.append(
                f"{rel} product_version={payload.get('product_version')!r}, expected {EXPECTED_VERSION!r}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the DataVision production source baseline.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors = check(root)
    result = {
        "product": "DataVision AI",
        "version": EXPECTED_VERSION,
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif errors:
        print("Production baseline: FAIL")
        for error in errors:
            print(f"- {error}")
    else:
        print(f"Production baseline: OK (v{EXPECTED_VERSION})")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
