# DataVision AI v2.7 — Connectors & Refresh

## Objectif

Faire évoluer DataVision d'un outil centré sur l'upload vers une plateforme capable de maintenir des datasets analytiques à jour depuis des systèmes SQL réels, tout en conservant les invariants de versioning, sécurité et reproductibilité.

## Architecture

```text
PostgreSQL / MySQL
        │
        ▼
Data Connector
  credentials chiffrés
        │
        ▼
Connector Source
 table ou SELECT/CTE read-only
        │
        ├── Full refresh
        │
        └── Incremental refresh + watermark
        │
        ▼
Refresh Run
        │
        ▼
Dataset immuable vN
        │
        ├── RBAC / RLS / CLS
        ├── Semantic Layer
        ├── Analytics / ML
        ├── Dashboards
        └── Reports
```

## Connecteurs

Types supportés en v2.7 :

- PostgreSQL : driver SQLAlchemy `postgresql+psycopg` ;
- MySQL : driver SQLAlchemy `mysql+pymysql`.

Un connecteur conserve le host, port, base, username, politique TLS et options non sensibles. Le mot de passe est chiffré avec Fernet avant persistance dans le metadata store, avec une clé dédiée `CONNECTOR_SECRET_KEY` lorsque configurée.

L'API ne renvoie jamais `password_ciphertext` ni le secret déchiffré.

## Source discovery

Le moteur utilise l'inspection SQLAlchemy pour retourner :

- schémas applicatifs ;
- tables ;
- colonnes ;
- types ;
- nullabilité.

Les schémas système courants sont filtrés.

## Sources read-only

Une source peut être :

1. une table qualifiée, par exemple `public.orders` ;
2. une requête personnalisée commençant par `SELECT` ou `WITH`.

Les requêtes personnalisées sont limitées à une seule instruction et les verbes de mutation/DDL courants sont rejetés. Cette validation applicative ne remplace pas un compte source SQL configuré en lecture seule.

## Full refresh

Le résultat complet de la source est matérialisé dans une nouvelle version immutable.

```text
v3 + refresh complet → v4
```

## Incremental refresh

Une source incrémentale définit une colonne watermark. Après un premier chargement complet, DataVision ajoute une condition de type :

```sql
WHERE updated_at > :dv_watermark
ORDER BY updated_at
```

Les nouvelles lignes sont concaténées au dataset brut précédent puis enregistrées comme nouvelle version.

Le moteur interne utilise `load_dataframe_raw()` uniquement pour le lifecycle de refresh afin d'éviter de matérialiser par erreur un sous-ensemble RLS. Toutes les analyses utilisateur continuent d'utiliser `load_dataframe()` et restent gouvernées.

## Schema drift

Le schéma observé est persisté par source. Chaque refresh calcule :

```json
{
  "detected": true,
  "added": ["new_col"],
  "removed": ["old_col"],
  "type_changed": []
}
```

Politique `warn` : le refresh continue et le drift est enregistré.

Politique `fail` : suppression de colonne ou changement de type bloque la matérialisation.

## Freshness

La fraîcheur est calculée à partir du dernier refresh réussi et d'un SLA en minutes.

- `fresh` : âge <= SLA ;
- `warning` : âge > 80 % du SLA ;
- `stale` : âge > SLA ;
- `error` : dernier run en erreur ;
- `refreshing` : run en cours ;
- `never` : jamais matérialisé.

## Scheduler

`refresh_schedules` conserve l'intervalle et `next_run_at`. Le worker vérifie les échéances toutes les 30 secondes.

Le claim utilise un `UPDATE ... WHERE next_run_at=:expected` afin que deux workers ne revendiquent pas la même échéance dans le cas normal.

Le schedule produit ensuite un job `connector_refresh` dans Redis.

## Observabilité

Table `refresh_runs` :

- run ID ;
- workspace ;
- source ;
- connecteur ;
- dataset before / after ;
- mode ;
- trigger ;
- job ID ;
- lignes fetched / written ;
- watermarks ;
- schema drift ;
- timestamps ;
- erreur.

La synthèse workspace calcule également : nombre de connecteurs, erreurs, sources par état de fraîcheur, succès des runs, durée moyenne, volume total et sources planifiées.

## Permissions

- `connectors:read` : tous les rôles ;
- `connectors:manage` : Owner/Admin ;
- `refresh:run` : Owner/Admin/Data Scientist.

Les jobs asynchrones réévaluent ces permissions au moment de l'exécution.

## Limites v2.7

- pas encore de SQL Server, Oracle, Snowflake, BigQuery ou fichiers cloud ;
- pas de CDC natif/log-based ;
- pas de vault externe HashiCorp/AWS/Azure/GCP ;
- pas encore de cron calendaire complexe ;
- pas de retry/backoff configurable par source ;
- schema contracts avancés prévus pour v2.8.
