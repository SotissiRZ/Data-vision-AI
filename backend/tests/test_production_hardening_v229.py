from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_health_endpoints_and_compose_healthchecks_exist():
    main = (ROOT / 'backend/app/main.py').read_text()
    sandbox = (ROOT / 'sandbox/app/main.py').read_text()
    compose = (ROOT / 'docker-compose.yml').read_text()
    assert '@app.get("/health/live")' in main
    assert '@app.get("/health/ready")' in main
    assert '@app.get("/health/live")' in sandbox
    assert '@app.get("/health/ready")' in sandbox
    for service in ('postgres:', 'redis:', 'api:', 'sandbox:', 'worker:', 'web:'):
        assert service in compose
    assert compose.count('healthcheck:') >= 6
    assert 'condition: service_healthy' in compose


def test_ci_security_release_workflows_are_present():
    ci = (ROOT / '.github/workflows/ci.yml').read_text()
    security = (ROOT / '.github/workflows/security.yml').read_text()
    release = (ROOT / '.github/workflows/release.yml').read_text()
    assert 'pytest -q' in ci
    assert 'npm run build' in ci
    assert 'playwright' in ci.lower()
    assert 'docker compose config -q' in ci
    assert 'pip-audit' in security
    assert 'trivy' in security.lower()
    assert 'cyclonedx' in release.lower()
    assert 'sbom' in release.lower()
    assert 'scripts/release.py' in release


def test_frontend_has_typecheck_and_e2e_contract():
    package = (ROOT / 'frontend/package.json').read_text()
    config = (ROOT / 'frontend/playwright.config.ts').read_text()
    smoke = (ROOT / 'frontend/e2e/smoke.spec.ts').read_text()
    health = (ROOT / 'frontend/app/api/health/route.ts').read_text()
    assert '"typecheck"' in package
    assert '"test:e2e"' in package
    assert '@playwright/test' in package
    assert 'baseURL' in config
    assert '@smoke' in smoke
    assert 'datavision-web' in health


def test_reproducible_release_scripts_exist():
    release = (ROOT / 'scripts/release.py').read_text()
    verify = (ROOT / 'scripts/verify_release.py').read_text()
    assert 'FIXED_ZIP_TIME' in release
    assert 'RELEASE_MANIFEST.json' in release
    assert 'sha256' in release.lower()
    assert 'testzip' in verify
