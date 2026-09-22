import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _datavision_test_auth_mode(monkeypatch):
    """Legacy unit suites exercise services without browser authentication.

    Production/default configuration remains AUTH_MODE=required. Tests opt into the
    explicit development-only anonymous mode unless a test overrides it.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_mode", "local_dev")
    monkeypatch.setattr(settings, "app_env", "test")
    # Keep unit tests fast/backward-compatible while production defaults remain hardened.
    monkeypatch.setattr(settings, "password_min_length", 8)
    monkeypatch.setattr(settings, "password_scrypt_n", 2**14)
    monkeypatch.setattr(settings, "password_scrypt_r", 8)
    monkeypatch.setattr(settings, "password_scrypt_p", 1)
