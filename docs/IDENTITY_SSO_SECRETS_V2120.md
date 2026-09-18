# DataVision AI v2.12 — Identity, SSO & Secret Management

## Objectif

La v2.12 renforce la frontière Enterprise sur trois axes : sessions révocables côté serveur, SSO OIDC moderne et coffre de secrets versionné. Elle complète l'authentification locale de v2.1 sans supprimer le mode local ni les rôles/workspaces existants.

## Sessions Enterprise persistantes

L'authentification locale et OIDC crée désormais une session persistante dans `auth_sessions`.

```text
Login / SSO
   ↓
Session serveur
   ├── access token court (60 min par défaut)
   └── refresh token rotatif (14 jours par défaut)
           ↓
       refresh
           ↓
ancien refresh token invalidé
nouveau refresh token émis
```

Le refresh token brut n'est pas stocké : seul son SHA-256 est conservé. L'access token contient un `sid` et chaque requête Enterprise vérifie que la session correspondante n'est ni révoquée ni expirée. Un utilisateur peut lister ses sessions, en révoquer une ou fermer toutes ses autres sessions.

Les tokens historiques sans `sid` restent acceptés jusqu'à leur expiration afin de ne pas casser brutalement une installation v2.11 existante.

## SSO OIDC Authorization Code + PKCE

Un Owner/Admin peut enregistrer un fournisseur OIDC par workspace. DataVision supporte :

- discovery `/.well-known/openid-configuration` ;
- Authorization Code ;
- PKCE S256 ;
- `state` à usage unique et expirant ;
- `nonce` ;
- validation cryptographique des ID tokens RS256 via JWKS ;
- vérification `iss`, `aud`, `exp` et `nonce` ;
- restriction facultative par domaines email ;
- provisioning JIT ;
- rôle JIT par défaut ;
- mapping durable `provider + subject → utilisateur DataVision`.

Le client secret OIDC est chiffré au repos et n'est jamais retourné par les endpoints de lecture.

### Flux

```text
Navigateur
   ↓
GET fournisseurs publics
   ↓
POST /auth/oidc/{provider}/start
   ↓
state + nonce + PKCE verifier/challenge
   ↓
Identity Provider
   ↓
authorization code
   ↓
POST /auth/oidc/exchange
   ↓
Token endpoint + JWKS validation
   ↓
JIT user / workspace membership
   ↓
Session DataVision persistante
```

## Secret Vault versionné

Le coffre de secrets est une ressource de workspace administrée par Owner/Admin. L'API ne renvoie jamais la valeur d'un secret ni son ciphertext.

Trois providers sont disponibles :

1. `local_encrypted` : valeur chiffrée localement avec la clé DataVision ;
2. `env` : référence vers une variable d'environnement, sans recopier sa valeur dans le metadata store ;
3. `vault_kv2` : référence vers HashiCorp Vault KV v2, avec token Vault chiffré au repos.

Chaque rotation crée une nouvelle entrée dans `secret_vault_versions`, incrémente `current_version` et marque la version précédente `retired`.

```text
secret logical name
      ↓
version 1  retired
      ↓
version 2  retired
      ↓
version 3  active
```

Pour Vault KV v2, DataVision appelle :

```text
GET {vault_url}/v1/{mount}/data/{path}
X-Vault-Token: <resolved secret>
```

et lit le champ configuré dans la réponse KV v2.

## Réseau et sécurité

Les appels externes OIDC/Vault appliquent une validation d'URL. Hors environnement de développement, HTTPS est requis. Les URL contenant des credentials sont refusées. Les résolutions DNS vers loopback, réseaux privés, link-local, multicast ou plages réservées sont bloquées pour les appels externes afin de limiter le risque SSRF.

Le support OIDC v2.12 est volontairement limité à `RS256`. Les autres algorithmes, SCIM, MFA/WebAuthn, KMS/HSM externe et politiques de session avancées restent des extensions futures.

## API principale

```text
POST /api/v1/auth/refresh
GET  /api/v1/auth/sessions
POST /api/v1/auth/sessions/{session_id}/revoke
POST /api/v1/auth/logout-all

GET  /api/v1/auth/oidc/providers
POST /api/v1/auth/oidc/{provider_id}/start
POST /api/v1/auth/oidc/exchange

GET    /api/v1/workspaces/{workspace_id}/identity/oidc
POST   /api/v1/workspaces/{workspace_id}/identity/oidc
DELETE /api/v1/workspaces/{workspace_id}/identity/oidc/{provider_id}

GET  /api/v1/workspaces/{workspace_id}/secrets
POST /api/v1/workspaces/{workspace_id}/secrets
POST /api/v1/workspaces/{workspace_id}/secrets/{secret_id}/rotate
POST /api/v1/workspaces/{workspace_id}/secrets/{secret_id}/test
```

## Interface

La zone **Gouverner → Identité & Secrets** regroupe :

- sessions actives/révoquées ;
- fermeture des autres sessions ;
- fournisseurs OIDC ;
- configuration JIT ;
- coffre de secrets ;
- rotation et test de résolution ;
- séparation Owner/Admin vs utilisateurs non administrateurs.

La page de connexion Enterprise affiche automatiquement les fournisseurs SSO actifs.
