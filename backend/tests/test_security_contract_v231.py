from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mfa_antivirus_kms_routes_and_services_exist():
    enterprise = (ROOT / "backend/app/api/routes/enterprise.py").read_text()
    datasets = (ROOT / "backend/app/api/routes/datasets.py").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()
    requirements = (ROOT / "backend/requirements.txt").read_text()

    for route in [
        '"/auth/mfa/status"',
        '"/auth/mfa/webauthn/register/options"',
        '"/auth/mfa/webauthn/register/verify"',
        '"/auth/mfa/webauthn/login/verify"',
    ]:
        assert route in enterprise
    assert "scan_upload(" in datasets
    assert "clamav/clamav" in compose
    assert "webauthn>=2.2,<3" in requirements


def test_secret_crypto_is_versioned_and_legacy_compatible():
    crypto = (ROOT / "backend/app/services/secret_crypto.py").read_text()
    connector = (ROOT / "backend/app/services/connector_service.py").read_text()
    assert '_PREFIX = "dvkms1"' in crypto
    assert "AESGCM" in crypto
    assert "legacy_fernet_decrypt" in crypto
    assert "from app.services.secret_crypto import encrypt_secret, decrypt_secret" in connector


def test_frontend_exposes_passkey_management_and_mfa_login():
    page = (ROOT / "frontend/app/page.tsx").read_text()
    api = (ROOT / "frontend/lib/api.ts").read_text()
    assert "Authentification multifacteur" in page
    assert "navigator.credentials.create" in page
    assert "navigator.credentials.get" in page
    assert "verifyEnterpriseWebAuthnLogin" in api
    assert "beginEnterpriseWebAuthnRegistration" in api
