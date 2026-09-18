# DataVision AI — v2.7.0

DataVision AI est un **Data Intelligence Workspace local, installable, gouverné et collaboratif** couvrant le cycle : connecter → versionner → contrôler → analyser → modéliser → expliquer → décider → publier → revoir.

## Ports

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

Les ports 3000 et 8000 ne sont pas utilisés.

## Nouveau dans v2.7.0 — Sources & Refresh

La zone **Gouverner → Sources & Refresh** transforme l'import ponctuel en véritable couche d'ingestion gouvernée.

### Connecteurs SQL réels

- PostgreSQL via `psycopg` ;
- MySQL via `PyMySQL` ;
- test de connexion ;
- découverte des schémas, tables et colonnes ;
- source depuis une table ou une requête SQL read-only ;
- TLS configurable `disable / prefer / require` selon le moteur.

Les mots de passe ne sont jamais renvoyés par l'API. Ils sont chiffrés au repos avec Fernet à partir de `CONNECTOR_SECRET_KEY` (fallback `AUTH_SECRET`). Pour un déploiement partagé, `AUTH_SECRET` doit être robuste, sauvegardé et géré comme une clé de production. L'intégration à un vault externe reste une étape ultérieure.

### Refresh versionné

Chaque refresh matérialise une nouvelle version immuable du dataset :

```text
Source SQL
   ↓
Refresh
   ↓
Dataset v1
   ↓
Refresh
   ↓
Dataset v2
   ↓
Analytics / ML / AI / Report
```

La version précédente reste disponible pour rollback, audit et reproductibilité.

### Full et incremental refresh

Le mode incrémental conserve un **watermark** sur une colonne telle que `updated_at`, `event_id` ou `id`.

```text
watermark actuel = 12500
        ↓
WHERE id > 12500
        ↓
nouvelles lignes uniquement
        ↓
append vers une nouvelle version
        ↓
nouveau watermark
```

Le refresh n'écrase jamais la version précédente.

### Scheduler

Les sources peuvent être exécutées :

- manuellement ;
- toutes les heures ;
- toutes les 6 h ;
- toutes les 12 h ;
- quotidiennement ;
- hebdomadairement ;
- avec un intervalle personnalisé entre 15 minutes et 30 jours via l'API.

Le worker revendique atomiquement les schedules arrivés à échéance avant de créer un job Redis. Cela réduit le risque de double déclenchement lorsque plusieurs workers tournent simultanément.

### Freshness SLA

Chaque source possède un SLA de fraîcheur et un état explicite :

```text
fresh
warning
stale
refreshing
error
never
```

`warning` signifie que plus de 80 % du SLA est consommé. `stale` signifie que le SLA est dépassé.

### Schema drift

DataVision compare le schéma courant au schéma du refresh précédent :

- colonnes ajoutées ;
- colonnes supprimées ;
- types modifiés.

Deux politiques sont disponibles :

- `warn` : poursuivre et enregistrer le drift ;
- `fail` : bloquer les changements destructifs avant matérialisation.

### Observabilité

Chaque exécution conserve :

- source et connecteur ;
- trigger manuel ou planifié ;
- mode full/incremental ;
- dataset avant/après ;
- nombre de lignes lues et matérialisées ;
- watermark avant/après ;
- schema drift ;
- début/fin ;
- erreur éventuelle ;
- job asynchrone associé.

La page **Sources & Refresh** présente le taux de succès, la durée moyenne, les volumes ingérés, les sources stale et l'historique des runs.

### RBAC v2.7

| Rôle | Voir sources | Tester / gérer credentials | Lancer refresh | Planifier |
|---|---:|---:|---:|---:|
| Owner | ✓ | ✓ | ✓ | ✓ |
| Admin | ✓ | ✓ | ✓ | ✓ |
| Data Scientist | ✓ | — | ✓ | — |
| Analyst | ✓ | — | — | — |
| Viewer | ✓ | — | — | — |

Les refresh asynchrones reconstruisent le contexte utilisateur/workspace avant exécution.

## Validation v2.7.0

```text
Backend pytest                 : 45 passed
Python compileall              : OK
TS/TSX syntax                  : OK
strictNullChecks ciblé         : OK
Credential encryption          : testé
Incremental refresh            : testé
Immutable dataset versions     : testé
Freshness SLA                  : testé
Schema drift fail policy       : testé
Atomic scheduler claim         : testé
Tenant-aware refresh job       : testé
Ports                          : 3005 / 8005
```

Le build Docker/Next complet reste à confirmer sur la machine cible avant validation frontend de production. Les tests de connexion PostgreSQL/MySQL réels nécessitent évidemment un serveur cible accessible ; la logique des drivers, credentials, refresh et scheduler est implémentée, mais aucun serveur externe n'est simulé comme « validé ».

## Installation Docker

```powershell
cp .env.example .env
docker compose build web
docker compose build api
docker compose up -d
docker compose ps
```

Puis ouvrir :

```text
http://localhost:3005
```

## Documentation

Les documents principaux sont dans `docs/` :

- `CONNECTORS_REFRESH_V270.md`
- `VALIDATION_V270.md`
- `COLLABORATION_REVIEW_V260.md`
- `PROACTIVE_INTELLIGENCE_V250.md`
- `SEMANTIC_ORCHESTRATION_V240.md`
- `SEMANTIC_LAYER_V2.md`
- `TENANT_AWARE_SECURITY.md`
- `REPORT_INTELLIGENCE.md`
- `DASHBOARD_BUILDER.md`
- `MARKET_BENCHMARK_2026.md`
- `PRODUCT_STRATEGY_2026.md`
- `ARCHITECTURE.md`
- `ROADMAP_EXECUTION.md`

## Principes non négociables

- aucun LLM comme calculatrice statistique ;
- données originales non détruites ;
- refresh et transformations versionnés ;
- analyses reproductibles ;
- credentials non exposés par l'API ;
- requêtes de sources personnalisées limitées à la lecture seule ;
- gouvernance appliquée au pipeline analytique complet ;
- aucune fonctionnalité fictive présentée comme implémentée ;
- décisions humaines documentées avant certification des actifs analytiques.
