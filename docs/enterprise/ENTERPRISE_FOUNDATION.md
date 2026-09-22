# DataVision AI v2.1 — Entreprise Foundation

## Objectif

La v2.1 introduit la première fondation multi-utilisateur et gouvernée sans casser le mode local historique. Le produit reste utilisable en mode analytique local, tandis que le nouvel espace **Gouverner** permet d'activer une identité locale et de travailler dans des organisations/workspaces.

## Implémenté

### Identité locale

- bootstrap initial d'un propriétaire ;
- connexion email/mot de passe ;
- mots de passe dérivés avec `hashlib.scrypt` + sel aléatoire ;
- bearer token signé HMAC-SHA256 avec expiration ;
- endpoint `/auth/me` ;
- durée du token configurable par `ACCESS_TOKEN_MINUTES`.

> La v2.1 n'est pas encore une implémentation OIDC/SSO et ne possède pas encore de refresh token.

### Organisations et workspaces

- organisation créée au bootstrap ;
- plusieurs workspaces par organisation ;
- membres par workspace ;
- rôles : `owner`, `admin`, `data_scientist`, `analyst`, `viewer` ;
- liaison explicite d'un dataset à un workspace.

### RBAC

Les permissions sont déterministes et explicites :

- `workspace:manage`
- `members:manage`
- `dataset:read`
- `dataset:write`
- `analysis:run`
- `model:run`
- `publish:write`
- `audit:read`
- `jobs:manage`
- `policies:manage`

Les nouvelles routes Entreprise appliquent le RBAC. Les routes analytiques historiques ne sont pas encore toutes migrées vers un contexte tenant-aware ; cette limitation reste **partial**, pas `implemented`.

### Metadata store

Les métadonnées Entreprise sont stockées via SQLAlchemy :

- PostgreSQL en déploiement Docker ;
- SQLite local de secours si PostgreSQL n'est pas disponible et que `METADATA_FALLBACK_SQLITE=true`.

Tables principales :

- `users`
- `organizations`
- `organization_members`
- `workspaces`
- `workspace_members`
- `workspace_datasets`
- `access_policies`
- `audit_logs`
- `jobs`

### Politiques lignes / colonnes

La v2.1 introduit un registre de politiques avec :

- colonnes autorisées ;
- filtres de lignes ;
- rôle ciblé ;
- traçabilité auteur/date ;
- endpoint de **governed preview** qui applique réellement les politiques au DataFrame avant restitution.

Le moteur accepte notamment `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `in`, `between`, `is_null`, `not_null`.

**Limite v2.1 :** l'application automatique de ces politiques à toutes les analyses statistiques, SQL, ML, dashboards et rapports est planifiée pour la migration tenant-aware v2.2. Une politique ne doit donc pas être considérée comme une RLS Entreprise globale tant que cette migration n'est pas achevée.

### Audit log

Événements actuellement audités :

- bootstrap ;
- login ;
- création workspace ;
- ajout/modification membre ;
- liaison dataset ;
- création/modification politique ;
- governed preview ;
- soumission/annulation de jobs.

### Jobs asynchrones

Un worker Redis réel est ajouté au `docker-compose.yml`.

Types de jobs :

- `automl`
- `ai_analysis`
- `forecast`
- `report`

États :

- `queued`
- `running`
- `completed`
- `failed`
- `cancel_requested`
- `cancelled`

L'annulation d'un job encore en file est effective. Pour un job déjà en cours, la v2.1 enregistre la demande d'annulation mais ne force pas encore l'interruption préemptive d'un calcul scikit-learn déjà engagé.

## Interface

Une nouvelle zone principale **Gouverner** est ajoutée à l'architecture v2 :

- état Entreprise ;
- initialisation / connexion ;
- sélection et création de workspaces ;
- membres et rôles ;
- datasets gouvernés ;
- politiques d'accès ;
- jobs asynchrones ;
- journal d'audit.

Le but est d'éviter de disperser la gouvernance dans les écrans analytiques.

## Endpoints principaux

```text
POST /api/v1/auth/bootstrap
POST /api/v1/auth/login
GET  /api/v1/auth/me
GET  /api/v1/enterprise/status

POST /api/v1/workspaces
GET  /api/v1/workspaces/{workspace_id}
POST /api/v1/workspaces/{workspace_id}/members
POST /api/v1/workspaces/{workspace_id}/datasets
GET  /api/v1/workspaces/{workspace_id}/policies
POST /api/v1/workspaces/{workspace_id}/policies
GET  /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/governed-preview

GET  /api/v1/audit
POST /api/v1/jobs
GET  /api/v1/jobs
GET  /api/v1/jobs/{job_id}
POST /api/v1/jobs/{job_id}/cancel
```

## Sécurité de déploiement

Avant tout usage partagé :

1. remplacer `AUTH_SECRET` dans `.env` ;
2. utiliser HTTPS devant le service ;
3. ne pas exposer PostgreSQL/Redis publiquement ;
4. migrer vers OIDC/SSO pour les environnements d'entreprise ;
5. activer un gestionnaire de secrets ;
6. terminer l'enforcement tenant-aware global avant de revendiquer une isolation Entreprise complète.
