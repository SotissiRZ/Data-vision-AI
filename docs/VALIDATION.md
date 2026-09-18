# Validation actuelle — DataVision AI v2.12.0

La référence détaillée est `VALIDATION_V2120.md`.

```text
Backend pytest                  : 64 passed
Python compileall               : OK
TS/TSX ciblé strictNullChecks   : OK
Ports                           : 3005 / 8005
```

Les tests v2.12 couvrent sessions persistantes, rotation/revocation de refresh tokens, OIDC Authorization Code + PKCE, vérification cryptographique RS256/JWKS, provisioning JIT, secret vault versionné, références environnement et HashiCorp Vault KV v2.

Le build Docker/Next complet, un IdP OIDC réel et un serveur Vault externe doivent encore être confirmés sur la machine cible avec réseau et credentials réels.
