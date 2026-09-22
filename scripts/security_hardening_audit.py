#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8", errors="ignore")


def check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "status": "pass" if ok else "fail", "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="compliance/SECURITY_HARDENING_AUDIT.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    config = read(root, "backend/app/core/config.py")
    main_py = read(root, "backend/app/main.py")
    auth = read(root, "backend/app/services/auth_service.py")
    tenant = read(root, "backend/app/services/tenant_access.py")
    env = read(root, ".env.example")
    frontend_api = read(root, "frontend/lib/api.ts")
    page = read(root, "frontend/app/page.tsx")
    next_cfg = read(root, "frontend/next.config.mjs")
    rego = read(root, "policies/kubernetes/datavision.rego")
    sandbox_worker = read(root, "sandbox/app/kernel_worker.py")
    backend_dockerfile = read(root, "backend/Dockerfile")
    frontend_dockerfile = read(root, "frontend/Dockerfile")
    compose = read(root, "docker-compose.yml")

    checks: list[dict[str, Any]] = []
    checks.append(check("auth_required_default", 'auth_mode: str = "required"' in config and "AUTH_MODE=required" in env))
    checks.append(check("local_dev_blocked_in_production", 'settings.auth_mode == "local_dev" and settings.app_env.lower() != "production"' in tenant))
    checks.append(check("api_docs_disabled_default", "api_docs_enabled: bool = False" in config and "API_DOCS_ENABLED=false" in env))
    checks.append(check("cors_not_wildcard", "CORS_ORIGINS=*" not in env and 'cors_origins: str = "*"' not in config))
    first_run = read(root, "backend/app/services/first_run_setup.py")
    enterprise_routes = read(root, "backend/app/api/routes/enterprise.py")
    checks.append(check("first_run_setup_guard", all(x in first_run + enterprise_routes for x in ("local_first_run_allowed", "httponly=True", 'samesite="strict"', "validate_setup_token", "invalidate_setup_token"))))
    checks.append(check("password_memory_hard_hash", "hashlib.scrypt" in auth and "hmac.compare_digest" in auth))
    checks.append(check("password_policy_current_baseline", 'password_min_length: int = 8' in config and 'password_scrypt_n: int = 131072' in config and 'PASSWORD_MIN_LENGTH=8' in env))
    checks.append(check("demo_account_development_only", 'demo_account_enabled: bool = True' in config and 'settings.app_env.lower() in {"development", "test"}' in auth and 'DEMO_ACCOUNT_ENABLED=true' in env and 'production_demo_account_must_be_disabled' in read(root, "scripts/config_doctor.py")))
    checks.append(check("login_throttling", all(x in auth for x in ("enforce_login_throttle", "record_login_failure", "locked_until"))))
    checks.append(check("revocable_sessions_and_refresh_rotation", all(x in auth for x in ("validate_session_payload", "refresh_token_hash", "next_refresh", "revoked_at"))))
    checks.append(check("browser_tokens_session_scoped", "sessionStorage.getItem('dv_enterprise_token')" in frontend_api and "localStorage.getItem('dv_enterprise_token')" not in page + frontend_api))
    checks.append(check("security_headers", all(x in main_py for x in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy", "Strict-Transport-Security"))))
    checks.append(check("frontend_csp", "Content-Security-Policy" in next_cfg and "frame-ancestors 'none'" in next_cfg and "object-src 'none'" in next_cfg))
    checks.append(check("kubernetes_least_privilege", all(x in rego for x in ("allowPrivilegeEscalation", "RuntimeDefault", "capabilities.drop"))))
    checks.append(check("rego_no_unsafe_negated_index", "not c.securityContext.capabilities.drop[_]" not in rego))
    checks.append(check("sandbox_execution_isolated", "datavision-cell" in sandbox_worker and "exec(compile(" in sandbox_worker))
    checks.append(check("application_containers_non_root", "USER 10001:10001" in backend_dockerfile and "USER 10001:10001" in frontend_dockerfile))
    checks.append(check("compose_drops_linux_capabilities", compose.count("cap_drop:") >= 7 and compose.count("no-new-privileges:true") >= 7))

    dangerous_hits: list[str] = []
    dynamic_pattern = re.compile(r"shell\s*=\s*True|os\.system\s*\(|pickle\.loads\s*\(|yaml\.load\s*\(")
    scan_roots = [root / "backend", root / "scripts"]
    for base in scan_roots:
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if dynamic_pattern.search(line):
                    dangerous_hits.append(f"{path.relative_to(root)}:{lineno}")
    checks.append(check("no_high_risk_dynamic_execution_in_control_plane", not dangerous_hits, ", ".join(dangerous_hits[:10])))

    root_env = root / ".env"
    checks.append(check("no_runtime_env_in_release_root", not root_env.exists(), ".env is excluded from source release" if not root_env.exists() else ".env present"))

    passed = sum(item["status"] == "pass" for item in checks)
    failed = len(checks) - passed
    residual = [
        {
            "id": "R-EXT-PENTEST",
            "severity": "high",
            "status": "external_validation_required",
            "description": "Independent penetration test on the deployed target is required before production stable sign-off.",
        },
        {
            "id": "R-BROWSER-XSS",
            "severity": "medium",
            "status": "residual",
            "description": "Bearer tokens are session-scoped but remain JavaScript-accessible; CSP and dependency hygiene reduce, but do not eliminate, XSS token-theft risk.",
        },
        {
            "id": "R-TARGET-TLS-IAM",
            "severity": "high",
            "status": "external_validation_required",
            "description": "TLS termination, cloud IAM/KMS policies, firewalling and runtime image digests must be validated on the actual target infrastructure.",
        },
        {
            "id": "R-SUPPLY-CHAIN-LIVE",
            "severity": "high",
            "status": "ci_validation_required",
            "description": "pip-audit, npm audit, Trivy image/filesystem scan and Conftest must pass against the exact release build in CI.",
        },
        {
            "id": "R-PASSWORD-LENGTH",
            "severity": "medium",
            "status": "accepted_product_policy",
            "description": "The product minimum is 8 characters by product decision. For password-only production authentication, configure a longer minimum or require MFA according to the organization's policy.",
        },
    ]
    payload = {
        "product": "DataVision AI",
        "version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "audit": "security-hardening-static-v1",
        "summary": {"checks": len(checks), "passed": passed, "failed": failed},
        "checks": checks,
        "residual_risks": residual,
        "statement": "This audit is a deterministic source/configuration review and does not certify zero vulnerabilities.",
    }
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SECURITY_HARDENING_AUDIT: {'PASS' if failed == 0 else 'FAIL'} {passed}/{len(checks)}")
    for item in checks:
        print(f"{item['status'].upper()} {item['name']} {item['detail']}")
    if args.check and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
