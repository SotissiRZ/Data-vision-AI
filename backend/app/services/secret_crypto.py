from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_PREFIX = "dvkms1"  # compatibility contract for local envelope v1
_PREFIX_LOCAL = _PREFIX
_PREFIX_EXTERNAL = "dvkms2"


def _b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _derive(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _configured_keys() -> dict[str, bytes]:
    settings = get_settings()
    keys: dict[str, bytes] = {}
    primary_material = settings.secret_kms_key or settings.connector_secret_key or settings.auth_secret
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


def _vault_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.vault_addr.strip()
        and settings.vault_token.strip()
        and settings.vault_transit_mount.strip()
        and settings.vault_transit_key.strip()
    )


def _vault_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"X-Vault-Token": settings.vault_token.strip()}
    if settings.vault_namespace.strip():
        headers["X-Vault-Namespace"] = settings.vault_namespace.strip()
    return headers


def _vault_url(action: str) -> str:
    settings = get_settings()
    base = settings.vault_addr.strip().rstrip("/")
    mount = settings.vault_transit_mount.strip().strip("/")
    key = settings.vault_transit_key.strip().strip("/")
    return f"{base}/v1/{mount}/{action}/{key}"


def _vault_key_url(suffix: str = "") -> str:
    settings = get_settings()
    base = settings.vault_addr.strip().rstrip("/")
    mount = settings.vault_transit_mount.strip().strip("/")
    key = settings.vault_transit_key.strip().strip("/")
    tail = f"/{suffix.strip('/')}" if suffix else ""
    return f"{base}/v1/{mount}/keys/{key}{tail}"


def _vault_encrypt(value: str, *, aad: str) -> str:
    if not _vault_configured():
        raise RuntimeError("KMS Vault Transit sélectionné mais configuration incomplète.")
    settings = get_settings()
    payload = {
        "plaintext": base64.b64encode(value.encode("utf-8")).decode("ascii"),
        "context": base64.b64encode(aad.encode("utf-8")).decode("ascii"),
    }
    try:
        response = httpx.post(
            _vault_url("encrypt"),
            headers=_vault_headers(),
            json=payload,
            timeout=max(1, int(settings.vault_timeout_seconds)),
        )
        response.raise_for_status()
        ciphertext = str((response.json().get("data") or {}).get("ciphertext") or "")
    except Exception as exc:
        raise RuntimeError("Échec du chiffrement via Vault Transit") from exc
    if not ciphertext.startswith("vault:"):
        raise RuntimeError("Réponse Vault Transit invalide : ciphertext absent.")
    return f"{_PREFIX_EXTERNAL}:vault_transit:{_b64e(ciphertext.encode('utf-8'))}"


def _vault_decrypt(encoded: str, *, aad: str) -> str:
    if not _vault_configured():
        raise RuntimeError("Vault Transit requis pour déchiffrer ce secret.")
    settings = get_settings()
    ciphertext = _b64d(encoded).decode("utf-8")
    payload = {
        "ciphertext": ciphertext,
        "context": base64.b64encode(aad.encode("utf-8")).decode("ascii"),
    }
    try:
        response = httpx.post(
            _vault_url("decrypt"),
            headers=_vault_headers(),
            json=payload,
            timeout=max(1, int(settings.vault_timeout_seconds)),
        )
        response.raise_for_status()
        plaintext = str((response.json().get("data") or {}).get("plaintext") or "")
        if not plaintext:
            raise RuntimeError("plaintext absent")
        return base64.b64decode(plaintext).decode("utf-8")
    except Exception as exc:
        raise RuntimeError("Échec du déchiffrement via Vault Transit") from exc


def encrypt_secret(value: str, *, aad: str = "datavision-secret") -> str:
    if not value:
        return ""
    settings = get_settings()
    provider = str(settings.secret_kms_provider or "local").strip().lower()
    if provider == "vault_transit":
        return _vault_encrypt(value, aad=aad)
    if provider != "local":
        raise RuntimeError(f"Fournisseur KMS non supporté : {provider}")
    key_id = settings.secret_kms_key_id or "primary"
    key = _configured_keys()[key_id]
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), aad.encode("utf-8"))
    return f"{_PREFIX_LOCAL}:{key_id}:{_b64e(nonce)}:{_b64e(ciphertext)}"


def decrypt_secret(value: str | None, *, aad: str = "datavision-secret") -> str:
    if not value:
        return ""
    if value.startswith(_PREFIX_EXTERNAL + ":"):
        parts = value.split(":", 2)
        if len(parts) != 3 or parts[1] != "vault_transit":
            raise RuntimeError("Ciphertext KMS externe DataVision invalide")
        return _vault_decrypt(parts[2], aad=aad)
    if value.startswith(_PREFIX_LOCAL + ":"):
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
            plain = AESGCM(key).decrypt(_b64d(nonce), _b64d(ciphertext), aad.encode("utf-8"))
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
    provider = str(settings.secret_kms_provider or "local").strip().lower()
    if provider == "vault_transit":
        configured = _vault_configured()
        return {
            "scheme": "Vault Transit envelope",
            "provider": "vault_transit",
            "key_id": settings.vault_transit_key or "datavision",
            "dedicated_key": configured,
            "material_source": "external_kms",
            "external_kms": True,
            "hsm_capable": True,
            "hsm_backed": bool(settings.vault_transit_hsm_backed),
            "legacy_fernet_decrypt": True,
            "production_ready": configured,
        }
    dedicated = bool(settings.secret_kms_key)
    fallback = "secret_kms_key" if dedicated else "connector_secret_key" if settings.connector_secret_key else "auth_secret"
    return {
        "scheme": "AES-256-GCM envelope v1",
        "provider": "local",
        "key_id": settings.secret_kms_key_id or "primary",
        "dedicated_key": dedicated,
        "material_source": fallback,
        "external_kms": False,
        "hsm_capable": False,
        "hsm_backed": False,
        "legacy_fernet_decrypt": True,
        "production_ready": dedicated,
    }


def vault_key_status() -> dict[str, Any]:
    if not _vault_configured():
        raise RuntimeError("Vault Transit non configuré")
    settings = get_settings()
    try:
        response = httpx.get(
            _vault_key_url(), headers=_vault_headers(), timeout=max(1, int(settings.vault_timeout_seconds))
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
        return {
            "name": data.get("name") or settings.vault_transit_key,
            "latest_version": int(data.get("latest_version") or 0),
            "min_decryption_version": int(data.get("min_decryption_version") or 1),
            "min_encryption_version": int(data.get("min_encryption_version") or 0),
            "supports_rotation": True,
        }
    except Exception as exc:
        raise RuntimeError("Impossible de lire l’état de la clé Vault Transit") from exc


def rotate_kms_key(*, actor_user_id: str | None = None, organization_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    provider = str(settings.secret_kms_provider or "local").strip().lower()
    if provider != "vault_transit":
        raise RuntimeError("La rotation opérable automatique nécessite SECRET_KMS_PROVIDER=vault_transit")
    before = vault_key_status()
    try:
        response = httpx.post(
            _vault_key_url("rotate"), headers=_vault_headers(), json={}, timeout=max(1, int(settings.vault_timeout_seconds))
        )
        response.raise_for_status()
        after = vault_key_status()
        result = {
            "provider": "vault_transit",
            "key_id": settings.vault_transit_key,
            "previous_version": before.get("latest_version"),
            "new_version": after.get("latest_version"),
            "rotated": int(after.get("latest_version") or 0) > int(before.get("latest_version") or 0),
        }
        try:
            from app.services.metadata_store import execute, json_dumps, utcnow
            execute(
                """INSERT INTO kms_rotation_events(
                    id,provider,key_id,previous_version,new_version,actor_user_id,organization_id,status,created_at,details_json
                ) VALUES(:id,:provider,:key_id,:previous,:new,:actor,:org,:status,:created,:details)""",
                {
                    "id": str(uuid.uuid4()), "provider": "vault_transit", "key_id": settings.vault_transit_key,
                    "previous": result["previous_version"], "new": result["new_version"],
                    "actor": actor_user_id, "org": organization_id,
                    "status": "success" if result["rotated"] else "unchanged", "created": utcnow(),
                    "details": json_dumps(result),
                },
            )
        except Exception:
            pass
        return result
    except Exception as exc:
        raise RuntimeError("Échec de la rotation Vault Transit") from exc
