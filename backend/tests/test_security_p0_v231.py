import base64
import json
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.auth_service import bootstrap
from app.services.mfa_service import (
    begin_password_login,
    begin_registration,
    finish_password_login,
    finish_registration,
    mfa_status,
)
from app.services.secret_crypto import decrypt_secret, encrypt_secret, kms_status
from app.services.upload_security import scan_upload


def _configure(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(
        settings,
        "database_url",
        f"sqlite:///{tmp_path / 'metadata.db'}",
    )
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    monkeypatch.setattr(settings, "secret_kms_key", "test-kms-key-v231")
    monkeypatch.setattr(settings, "secret_kms_key_id", "test-primary")
    monkeypatch.setattr(settings, "secret_kms_previous_keys", "{}")
    monkeypatch.setattr(settings, "webauthn_enabled", True)
    monkeypatch.setattr(settings, "webauthn_rp_id", "localhost")
    monkeypatch.setattr(settings, "webauthn_origin", "http://localhost:3005")
    monkeypatch.setattr(settings, "antivirus_mode", "preferred")
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _fake_webauthn():
    class Descriptor:
        def __init__(self, id):
            self.id = id

    class Opts:
        def __init__(self, challenge):
            self.challenge = challenge

    def to_json(options):
        challenge = base64.urlsafe_b64encode(options.challenge).rstrip(b"=").decode()
        return json.dumps({"challenge": challenge, "rpId": "localhost"})

    class UV:
        REQUIRED = "required"

    return {
        "PublicKeyCredentialDescriptor": Descriptor,
        "UserVerificationRequirement": UV,
        "generate_registration_options": lambda **kwargs: Opts(b"register-challenge"),
        "generate_authentication_options": lambda **kwargs: Opts(b"login-challenge"),
        "options_to_json": to_json,
        "verify_registration_response": lambda **kwargs: SimpleNamespace(
            credential_id=b"credential-1",
            credential_public_key=b"public-key-1",
            sign_count=1,
        ),
        "verify_authentication_response": lambda **kwargs: SimpleNamespace(
            new_sign_count=2,
        ),
    }


def test_aesgcm_secret_roundtrip_and_status(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    encrypted = encrypt_secret("top-secret")
    assert encrypted.startswith("dvkms1:test-primary:")
    assert decrypt_secret(encrypted) == "top-secret"
    status = kms_status()
    assert status["dedicated_key"] is True
    assert status["production_ready"] is True


def test_eicar_upload_is_rejected_even_without_clamav(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    payload = (
        b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!"
        b"$H+H*"
    )
    with pytest.raises(ValueError, match="antivirus"):
        scan_upload("eicar.com.txt", payload)


def test_password_login_without_enrollment_remains_compatible(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    out = bootstrap(
        "owner@example.com",
        "password123",
        "Owner",
        "Example",
    )
    login = begin_password_login("owner@example.com", "password123")
    assert login["mfa_required"] is False
    assert login["access_token"]
    assert mfa_status(out["user"]["id"])["credential_count"] == 0


def test_webauthn_registration_and_login_challenge_flow(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    import app.services.mfa_service as mfa

    monkeypatch.setattr(mfa, "_require_webauthn", _fake_webauthn)
    out = bootstrap(
        "mfa@example.com",
        "password123",
        "MFA User",
        "Example",
    )
    user_id = out["user"]["id"]

    begin = begin_registration(user_id)
    status = finish_registration(
        user_id,
        begin["challenge_id"],
        {
            "id": "credential-1",
            "rawId": base64.urlsafe_b64encode(b"credential-1").rstrip(b"=").decode(),
            "type": "public-key",
            "response": {"transports": ["internal"]},
        },
        label="Laptop passkey",
    )
    assert status["enrolled"] is True
    assert status["credential_count"] == 1

    login = begin_password_login("mfa@example.com", "password123")
    assert login["mfa_required"] is True
    raw_id = base64.urlsafe_b64encode(b"credential-1").rstrip(b"=").decode()
    complete = finish_password_login(
        login["challenge_id"],
        {
            "id": raw_id,
            "rawId": raw_id,
            "type": "public-key",
            "response": {},
        },
    )
    assert complete["mfa_verified"] is True
    assert complete["access_token"]


def test_webauthn_challenge_cannot_be_replayed(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    import app.services.mfa_service as mfa

    monkeypatch.setattr(mfa, "_require_webauthn", _fake_webauthn)
    out = bootstrap("replay@example.com", "password123", "Replay", "Example")
    begin = begin_registration(out["user"]["id"])
    credential = {
        "id": "credential-1",
        "rawId": base64.urlsafe_b64encode(b"credential-1").rstrip(b"=").decode(),
        "type": "public-key",
        "response": {},
    }
    finish_registration(out["user"]["id"], begin["challenge_id"], credential)
    with pytest.raises(ValueError, match="déjà utilisé"):
        finish_registration(out["user"]["id"], begin["challenge_id"], credential)
