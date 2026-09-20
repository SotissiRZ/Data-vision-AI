from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backend_image_bundles_compliance_assets():
    dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "COPY compliance ./compliance" in dockerfile
    assert "context: ." in compose
    assert "dockerfile: backend/Dockerfile" in compose


def test_cdc_service_resolves_packaged_project_root():
    service = (ROOT / "backend/app/services/cdc_compliance.py").read_text(encoding="utf-8")
    assert "DATAVISION_PROJECT_ROOT" in service
    assert 'Path("/app")' in service
    assert 'CDC_COVERAGE_MATRIX.json' in service


def test_frontend_uses_same_origin_backend_proxy():
    api = (ROOT / "frontend/lib/api.ts").read_text(encoding="utf-8")
    config = (ROOT / "frontend/next.config.mjs").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "'/api/backend'" in api
    assert "source: '/api/backend/:path*'" in config
    assert "http://api:8005/api/v1" in compose
    assert "NEXT_PUBLIC_API_URL: /api/backend" in compose


def test_compliance_ui_has_retry_state():
    ui = (ROOT / "frontend/components/ComplianceCenter.tsx").read_text(encoding="utf-8")
    assert "loadError" in ui
    assert "Réessayer" in ui
