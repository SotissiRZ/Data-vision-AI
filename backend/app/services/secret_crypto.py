from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_PREFIX = "dvkms1"


def _b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _derive(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _configured_keys() -> dict[str, bytes]:
    settings = get_settings()
    keys: dict[str, bytes] = {}
    primary_material = (
        settings.secret_kms_key
        or settings.connector_secret_key
        or settings.auth_secret
    )
    keys[settings.secret_kms_key_id or "primary"] = _derive(primary_material)
    try:
        previous = json.loads(settings.secret_kms_previous_keys or "{}")
    except Exception:
        previous = {}
    if isinstance(previous, dict):
        for key_id, material in previous.items():
            if key_id and material:
                keys[str(key_id)] = _derive(str(material))
    return keys


def _legacy_fernet() -> Fernet:
    settings = get_settings()
    material = settings.connector_secret_key or settings.auth_secret
    raw = _derive(material)
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_secret(value: str, *, aad: str = "datavision-secret") -> str:
    if not value:
        return ""
    settings = get_settings()
    key_id = settings.secret_kms_key_id or "primary"
    key = _configured_keys()[key_id]
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        value.encode("utf-8"),
        aad.encode("utf-8"),
    )
    return f"{_PREFIX}:{key_id}:{_b64e(nonce)}:{_b64e(ciphertext)}"


def decrypt_secret(value: str | None, *, aad: str = "datavision-secret") -> str:
    if not value:
        return ""
    if value.startswith(_PREFIX + ":"):
        parts = value.split(":", 3)
        if len(parts) != 4:
            raise RuntimeError("Ciphertext KMS DataVision invalide")
        _prefix, key_id, nonce, ciphertext = parts
        keys = _configured_keys()
        key = keys.get(key_id)
        if key is None:
            raise RuntimeError(
                f"Clé KMS introuvable pour key_id={key_id}. "
                "Configurez SECRET_KMS_PREVIOUS_KEYS avant rotation."
            )
        try:
            plain = AESGCM(key).decrypt(
                _b64d(nonce),
                _b64d(ciphertext),
                aad.encode("utf-8"),
            )
            return plain.decode("utf-8")
        except Exception as exc:
            raise RuntimeError("Impossible de déchiffrer le secret KMS") from exc

    # Backward compatibility for credentials encrypted before v2.31.
    try:
        return _legacy_fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError(
            "Impossible de déchiffrer le secret legacy. Vérifiez AUTH_SECRET/CONNECTOR_SECRET_KEY."
        ) from exc


def kms_status() -> dict[str, Any]:
    settings = get_settings()
    dedicated = bool(settings.secret_kms_key)
    fallback = (
        "secret_kms_key"
        if dedicated
        else "connector_secret_key"
        if settings.connector_secret_key
        else "auth_secret"
    )
    return {
        "scheme": "AES-256-GCM envelope v1",
        "key_id": settings.secret_kms_key_id or "primary",
        "dedicated_key": dedicated,
        "material_source": fallback,
        "legacy_fernet_decrypt": True,
        "production_ready": dedicated,
    }
