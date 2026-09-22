#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_VERSION = "2.81.0"
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
    "compliance/TYPOGRAPHY_ACCEPTANCE.json",
    "compliance/COLLABORATION_ACCEPTANCE.json",
    "compliance/ENTREPRISE_ACCEPTANCE.json",
    "compliance/ASSISTANT_WINDOW_ACCEPTANCE.json",
    "compliance/HARDENING_ACCEPTANCE.json",
    "compliance/RESILIENCE_ACCEPTANCE.json",
    "compliance/SRE_ACCEPTANCE.json",
    "compliance/REGULATORY_COMPLIANCE_ACCEPTANCE.json",
    "compliance/QUALITY_REMEDIATION_ACCEPTANCE.json",
    "compliance/STORYTELLING_ACCEPTANCE.json",
    "compliance/MODEL_GATEWAY_ACCEPTANCE.json",
    "compliance/I18N_ACCESSIBILITY_ACCEPTANCE.json",
    "compliance/CLOUD_CDC_ACCEPTANCE.json",
    "compliance/WORKSPACE_ENVIRONMENT_ACCEPTANCE.json",
    "compliance/PERFORMANCE_SLO_ACCEPTANCE.json",
    "compliance/CDC_GAP_CLOSURE_ACCEPTANCE.json",
    "compliance/RELEASE_CANDIDATE_ACCEPTANCE.json",
    "compliance/RELEASE_INSTALLATION_ACCEPTANCE.json",
    "compliance/SECURITY_DOCUMENTATION_ACCEPTANCE.json",
    "scripts/security_documentation_acceptance.py",
    "scripts/security_hardening_audit.py",
    "compliance/SECURITY_HARDENING_AUDIT.json",
    "scripts/dependency_compatibility.py",
    "backend/tests/test_security_documentation_v281.py",
    "docs/RAPPORT_TECHNIQUE.md",
    "docs/GUIDE_UTILISATEUR.md",
    "docs/GUIDE_DEPLOIEMENT.md",
    "docs/RAPPORT_SECURITE.md",
    "docs/GUIDE_EXPLOITATION.md",
    "scripts/release_installation_acceptance.py",
    "scripts/config_doctor.py",
    "backend/tests/test_release_installation_v280.py",
    "docs/compliance/release/RELEASE_CANDIDATE_V2800.md",
    "docs/operations/upgrades/UPGRADE_V2790_TO_V2800.md",
    "policies/release_candidate.json",
    "upgrade-windows.ps1",
    "scripts/release_candidate_acceptance.py",
    "backend/tests/test_release_candidate_hardening_v279.py",
    "frontend/e2e/release-candidate.spec.ts",
    "docs/compliance/release/RELEASE_CANDIDATE_HARDENING_V2790.md",
    "scripts/cdc_gap_closure_acceptance.py",
    "docs/compliance/CDC_GAP_CLOSURE_V2780.md",
    "backend/app/services/product_plans.py",
    "backend/app/services/causal_inference.py",
    "backend/tests/test_cdc_gap_closure_v278.py",
    "scripts/performance_slo_acceptance.py",
    "scripts/performance_benchmark.py",
    "policies/performance_slo.json",
    "backend/app/services/performance_evidence.py",
    "backend/tests/test_performance_slo_v277.py",
    "docs/operations/PERFORMANCE_SLO_EVIDENCE_V2770.md",
    "scripts/workspace_environment_acceptance.py",
    "backend/app/services/workspace_environment.py",
    "backend/tests/test_workspace_environment_v276.py",
    "docs/operations/WORKSPACE_ENVIRONMENTS_V2760.md",
    "scripts/cloud_cdc_acceptance.py",
    "backend/app/services/cdc_ingestion.py",
    "backend/tests/test_cloud_cdc_v275.py",
    "docs/data/CLOUD_CDC_INGESTION_V2750.md",
    "scripts/i18n_accessibility_acceptance.py",
    "frontend/lib/i18n.ts",
    "frontend/e2e/accessibility.spec.ts",
    "backend/tests/test_i18n_accessibility_v274.py",
    "docs/ui-reporting/I18N_ACCESSIBILITY_V2740.md",
    "scripts/model_gateway_acceptance.py",
    "backend/app/assistant/providers/anthropic.py",
    "backend/app/assistant/providers/gemini.py",
    "backend/tests/assistant/test_model_gateway_v273.py",
    "scripts/storytelling_acceptance.py",
    "backend/app/services/storytelling.py",
    "backend/tests/test_storytelling_v272.py",
    "scripts/regulatory_compliance_acceptance.py",
    "scripts/quality_remediation_acceptance.py",
    "backend/app/services/quality_remediation.py",
    "backend/tests/test_quality_remediation_v271.py",
    "backend/app/services/regulatory_compliance.py",
    "backend/tests/test_regulatory_compliance_v2650.py",
    "frontend/components/RegulatoryCompliancePanel.tsx",
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
    "scripts/typography_acceptance.py",
    "scripts/collaboration_acceptance.py",
    "scripts/governance_acceptance.py",
    "scripts/entreprise_acceptance.py",
    "scripts/assistant_window_acceptance.py",
    "scripts/hardening_acceptance.py",
    "scripts/resilience_acceptance.py",
    "scripts/sre_acceptance.py",
    "backend/tests/test_frontend_assistant_window_v2570.py",
    "backend/tests/test_entreprise_hardening_v2580.py",
    "backend/tests/test_resilience_ha_v2590.py",
    "backend/tests/test_sre_operations_v2600.py",
    "backend/app/services/sre_operations.py",
    "deploy/helm/datavision/templates/keda-worker.yaml",
    "backend/app/services/schema_migrations.py",
    "backend/app/services/backup_service.py",
    "backend/app/services/session_security.py",
    "infra/otel-collector-config.yaml",
    "deploy/helm/datavision/Chart.yaml",
    "deploy/helm/datavision/values.yaml",
    "backend/app/services/entreprise_platform.py",
    "backend/tests/test_entreprise_platform_v2560.py",
    "backend/tests/test_frontend_entreprise_v2560.py",
    "compliance/GOVERNANCE_ACCEPTANCE.json",
    "backend/app/services/governance_control.py",
    "backend/tests/test_governance_control_v2550.py",
    "backend/tests/test_frontend_governance_v2550.py",
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
    "backend/tests/test_frontend_insights_nullability_v2531.py",
    "backend/tests/test_frontend_trust_center_v2532.py",
    "backend/tests/test_frontend_typography_v2533.py",
    "backend/tests/test_collaboration_v2540.py",
    "backend/tests/test_frontend_collaboration_v2540.py",
    "backend/app/services/ml_guardrails.py",
    "backend/app/services/insight_engine.py",
    "backend/app/assistant/agents.py",
    "frontend/lib/assistant/effects.ts",
    "frontend/e2e/mvp.spec.ts",
    "frontend/e2e/production.spec.ts",
    "scripts/production_acceptance.py",
    "scripts/production_signoff.py",
    "scripts/load_smoke.py",
    "production-acceptance-windows.ps1",
    "backend/tests/test_production_acceptance_v2660.py",
    "docs/compliance/release/PRODUCTION_ACCEPTANCE_V266.md",
    "docs/compliance/UAT_SIGNOFF_TEMPLATE.md",
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

    for rel in ("compliance/CDC_COVERAGE_MATRIX.json", "compliance/PRODUCTION_ACCEPTANCE.json", "compliance/MVP_ACCEPTANCE.json", "compliance/PREPARATION_ACCEPTANCE.json", "compliance/WORKSPACE_ACCEPTANCE.json", "compliance/ASSISTANT_ACCEPTANCE.json", "compliance/ASSISTANT_MULTIMODAL_ACCEPTANCE.json", "compliance/MULTI_AGENT_ACCEPTANCE.json", "compliance/SEMANTIC_ACCEPTANCE.json", "compliance/INSIGHT_ACCEPTANCE.json", "compliance/REPORT_ACCEPTANCE.json", "compliance/AUTOML_ACCEPTANCE.json", "compliance/ML_SAFETY_ACCEPTANCE.json", "compliance/XAI_ACCEPTANCE.json", "compliance/FORECASTING_ANOMALY_ACCEPTANCE.json", "compliance/TYPOGRAPHY_ACCEPTANCE.json", "compliance/COLLABORATION_ACCEPTANCE.json", "compliance/ENTREPRISE_ACCEPTANCE.json", "compliance/ASSISTANT_WINDOW_ACCEPTANCE.json", "compliance/HARDENING_ACCEPTANCE.json", "compliance/RESILIENCE_ACCEPTANCE.json", "compliance/SRE_ACCEPTANCE.json", "compliance/REGULATORY_COMPLIANCE_ACCEPTANCE.json", "compliance/QUALITY_REMEDIATION_ACCEPTANCE.json", "compliance/STORYTELLING_ACCEPTANCE.json", "compliance/MODEL_GATEWAY_ACCEPTANCE.json", "compliance/I18N_ACCESSIBILITY_ACCEPTANCE.json", "compliance/CLOUD_CDC_ACCEPTANCE.json", "compliance/WORKSPACE_ENVIRONMENT_ACCEPTANCE.json", "compliance/PERFORMANCE_SLO_ACCEPTANCE.json", "compliance/CDC_GAP_CLOSURE_ACCEPTANCE.json", "compliance/RELEASE_CANDIDATE_ACCEPTANCE.json", "compliance/RELEASE_INSTALLATION_ACCEPTANCE.json"):
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
