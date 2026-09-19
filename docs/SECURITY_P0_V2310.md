# DataVision v2.31.0 — Security P0 Closure

## WebAuthn

Endpoints :
- `GET /api/v1/auth/mfa/status`
- `POST /api/v1/auth/mfa/webauthn/register/options`
- `POST /api/v1/auth/mfa/webauthn/register/verify`
- `DELETE /api/v1/auth/mfa/webauthn/{credential_id}`
- `POST /api/v1/auth/mfa/webauthn/login/verify`

Les clés privées restent dans l’authenticator. DataVision ne stocke que l’identifiant du credential, la clé publique et le compteur de signature.

## Upload AV

Le fichier est scanné avant `save_upload`. `required` est fail-closed. Les résultats du scan sont enregistrés dans `upload_security_scans` avec SHA256, taille, moteur, statut et timestamp.

## Secret encryption

Les nouveaux secrets utilisent AES-GCM avec key ID. Le déchiffrement legacy Fernet reste disponible pendant migration. Le readiness production refuse un démarrage considéré prêt si `SECRET_KMS_KEY` dédié est absent.

## Configuration production minimale

```env
APP_ENV=production
ANTIVIRUS_MODE=required
SECRET_KMS_KEY=<secret fort injecté par le runtime>
SECRET_KMS_KEY_ID=prod-2026-01
WEBAUTHN_ENABLED=true
WEBAUTHN_RP_ID=datavision.example.com
WEBAUTHN_ORIGIN=https://datavision.example.com
```

Un KMS/HSM cloud externe natif reste une extension future ; la v2.31 fournit le contrat de rotation/key-id et l’enveloppe cryptographique locale dédiée.
