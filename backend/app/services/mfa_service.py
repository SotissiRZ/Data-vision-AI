from __future__ import annotations

import base64
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.services.auth_service import (
    create_authenticated_session,
    get_user,
    get_user_by_email,
    verify_password,
)
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow


def _b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _require_webauthn():
    settings = get_settings()
    if not settings.webauthn_enabled:
        raise RuntimeError("WebAuthn est désactivé par configuration.")
    try:
        from webauthn import (
            generate_authentication_options,
            generate_registration_options,
            verify_authentication_response,
            verify_registration_response,
        )
        from webauthn.helpers import options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
    except Exception as exc:
        raise RuntimeError(
            "Le runtime WebAuthn n'est pas disponible. Installez la dépendance 'webauthn'."
        ) from exc
    return {
        "generate_authentication_options": generate_authentication_options,
        "generate_registration_options": generate_registration_options,
        "verify_authentication_response": verify_authentication_response,
        "verify_registration_response": verify_registration_response,
        "options_to_json": options_to_json,
        "PublicKeyCredentialDescriptor": PublicKeyCredentialDescriptor,
        "UserVerificationRequirement": UserVerificationRequirement,
    }


def _new_challenge(user_id: str, challenge_type: str, challenge: bytes) -> str:
    settings = get_settings()
    challenge_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=max(1, int(settings.mfa_challenge_minutes)))
    execute(
        """INSERT INTO auth_mfa_challenges(
             id,user_id,challenge_type,challenge_b64,created_at,expires_at,used_at
           ) VALUES(:id,:user,:type,:challenge,:created,:expires,NULL)""",
        {
            "id": challenge_id,
            "user": user_id,
            "type": challenge_type,
            "challenge": _b64e(challenge),
            "created": now.isoformat(),
            "expires": expires.isoformat(),
        },
    )
    return challenge_id


def _consume_challenge(challenge_id: str, challenge_type: str) -> tuple[str, bytes]:
    row = fetch_one(
        "SELECT * FROM auth_mfa_challenges WHERE id=:id AND challenge_type=:type",
        {"id": challenge_id, "type": challenge_type},
    )
    if not row or row.get("used_at"):
        raise ValueError("Challenge MFA invalide ou déjà utilisé.")
    expires = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise ValueError("Challenge MFA expiré.")
    # Reserve before cryptographic verification to prevent replay; a failed ceremony requires a new challenge.
    execute(
        "UPDATE auth_mfa_challenges SET used_at=:now WHERE id=:id",
        {"now": utcnow(), "id": challenge_id},
    )
    return str(row["user_id"]), _b64d(str(row["challenge_b64"]))


def list_credentials(user_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        """SELECT id,credential_id,sign_count,transports_json,label,created_at,last_used_at,disabled_at
           FROM auth_webauthn_credentials WHERE user_id=:user ORDER BY created_at DESC""",
        {"user": user_id},
    )
    for row in rows:
        row["transports"] = json_loads(row.pop("transports_json", "[]"), [])
        row["active"] = not bool(row.get("disabled_at"))
        row["credential_id_preview"] = str(row.get("credential_id") or "")[:12]
        row.pop("credential_id", None)
    return rows


def mfa_status(user_id: str) -> dict[str, Any]:
    settings = get_settings()
    creds = list_credentials(user_id)
    return {
        "webauthn_enabled": bool(settings.webauthn_enabled),
        "enrolled": any(item["active"] for item in creds),
        "credential_count": sum(1 for item in creds if item["active"]),
        "credentials": creds,
        "policy": settings.mfa_policy,
        "rp_id": settings.webauthn_rp_id,
        "origin": settings.webauthn_origin,
    }


def _active_credential_rows(user_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        "SELECT * FROM auth_webauthn_credentials WHERE user_id=:user AND disabled_at IS NULL ORDER BY created_at",
        {"user": user_id},
    )


def begin_registration(user_id: str) -> dict[str, Any]:
    lib = _require_webauthn()
    settings = get_settings()
    user = get_user(user_id)
    if not user:
        raise KeyError("Utilisateur introuvable")
    descriptors = [
        lib["PublicKeyCredentialDescriptor"](id=_b64d(str(row["credential_id"])))
        for row in _active_credential_rows(user_id)
    ]
    options = lib["generate_registration_options"](
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user_id.encode("utf-8"),
        user_name=str(user["email"]),
        user_display_name=str(user.get("display_name") or user["email"]),
        exclude_credentials=descriptors,
    )
    challenge_id = _new_challenge(user_id, "registration", bytes(options.challenge))
    return {
        "challenge_id": challenge_id,
        "publicKey": json.loads(lib["options_to_json"](options)),
    }


def finish_registration(
    user_id: str,
    challenge_id: str,
    credential: dict[str, Any],
    *,
    label: str = "Passkey",
) -> dict[str, Any]:
    lib = _require_webauthn()
    settings = get_settings()
    challenge_user_id, challenge = _consume_challenge(challenge_id, "registration")
    if challenge_user_id != user_id:
        raise PermissionError("Challenge MFA associé à un autre utilisateur.")
    verified = lib["verify_registration_response"](
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=settings.webauthn_origin,
        require_user_verification=True,
    )
    credential_id = _b64e(bytes(verified.credential_id))
    public_key = _b64e(bytes(verified.credential_public_key))
    transports = (
        ((credential.get("response") or {}).get("transports"))
        if isinstance(credential, dict)
        else []
    ) or []
    execute(
        """INSERT INTO auth_webauthn_credentials(
             id,user_id,credential_id,public_key,sign_count,transports_json,label,created_at
           ) VALUES(:id,:user,:credential,:key,:count,:transports,:label,:created)""",
        {
            "id": str(uuid.uuid4()),
            "user": user_id,
            "credential": credential_id,
            "key": public_key,
            "count": int(verified.sign_count or 0),
            "transports": json_dumps(transports),
            "label": label.strip()[:160] or "Passkey",
            "created": utcnow(),
        },
    )
    return mfa_status(user_id)


def disable_credential(user_id: str, credential_row_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT id,user_id FROM auth_webauthn_credentials WHERE id=:id",
        {"id": credential_row_id},
    )
    if not row or str(row["user_id"]) != str(user_id):
        raise KeyError("Passkey introuvable")
    execute(
        "UPDATE auth_webauthn_credentials SET disabled_at=:now WHERE id=:id",
        {"now": utcnow(), "id": credential_row_id},
    )
    return mfa_status(user_id)


def begin_password_login(email: str, password: str, *, user_agent: str = "") -> dict[str, Any]:
    row = get_user_by_email(email)
    if not row or not row.get("is_active") or not verify_password(password, row["password_hash"]):
        raise ValueError("Email ou mot de passe incorrect.")
    credentials = _active_credential_rows(str(row["id"]))
    if not get_settings().webauthn_enabled or not credentials:
        auth = create_authenticated_session(
            row["id"], row["email"], provider="local", device_label="password", user_agent=user_agent
        )
        return {**auth, "user": get_user(row["id"]), "mfa_required": False}

    lib = _require_webauthn()
    descriptors = [
        lib["PublicKeyCredentialDescriptor"](id=_b64d(str(item["credential_id"])))
        for item in credentials
    ]
    options = lib["generate_authentication_options"](
        rp_id=get_settings().webauthn_rp_id,
        allow_credentials=descriptors,
        user_verification=lib["UserVerificationRequirement"].REQUIRED,
    )
    challenge_id = _new_challenge(str(row["id"]), "authentication", bytes(options.challenge))
    return {
        "mfa_required": True,
        "challenge_id": challenge_id,
        "publicKey": json.loads(lib["options_to_json"](options)),
        "user": {"id": row["id"], "email": row["email"], "display_name": row.get("display_name")},
    }


def finish_password_login(
    challenge_id: str,
    credential: dict[str, Any],
    *,
    user_agent: str = "",
) -> dict[str, Any]:
    lib = _require_webauthn()
    settings = get_settings()
    user_id, challenge = _consume_challenge(challenge_id, "authentication")
    raw_id = str(credential.get("rawId") or credential.get("id") or "")
    row = fetch_one(
        "SELECT * FROM auth_webauthn_credentials WHERE user_id=:user AND credential_id=:credential AND disabled_at IS NULL",
        {"user": user_id, "credential": raw_id},
    )
    if not row:
        # Some browsers return padded/base64 variants; normalize when possible.
        try:
            normalized = _b64e(_b64d(raw_id))
        except Exception:
            normalized = raw_id
        row = fetch_one(
            "SELECT * FROM auth_webauthn_credentials WHERE user_id=:user AND credential_id=:credential AND disabled_at IS NULL",
            {"user": user_id, "credential": normalized},
        )
    if not row:
        raise PermissionError("Passkey inconnue ou désactivée.")

    verified = lib["verify_authentication_response"](
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=settings.webauthn_origin,
        credential_public_key=_b64d(str(row["public_key"])),
        credential_current_sign_count=int(row.get("sign_count") or 0),
        require_user_verification=True,
    )
    execute(
        "UPDATE auth_webauthn_credentials SET sign_count=:count,last_used_at=:now WHERE id=:id",
        {
            "count": int(verified.new_sign_count or row.get("sign_count") or 0),
            "now": utcnow(),
            "id": row["id"],
        },
    )
    user = get_user(user_id)
    if not user or not user.get("is_active"):
        raise ValueError("Utilisateur introuvable ou inactif")
    auth = create_authenticated_session(
        user_id,
        user["email"],
        provider="webauthn",
        device_label="passkey",
        user_agent=user_agent,
        mfa_verified=True,
    )
    return {**auth, "user": user, "mfa_required": False, "mfa_verified": True}
