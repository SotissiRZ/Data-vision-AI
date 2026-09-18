# DataVision AI — v2.8.0

DataVision AI est un **Data Intelligence Workspace local, installable, gouverné et collaboratif** couvrant le cycle : connecter → versionner → contrôler → analyser → modéliser → expliquer → décider → publier → revoir.

## Ports

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

Les ports 3000 et 8000 ne sont pas utilisés.

## Nouveau dans v2.8.0 — Data Reliability & Lineage

La zone **Gouverner → Fiabilité & Lineage** transforme la qualité des données en une couche exécutable et gouvernée. Une donnée n'est plus seulement « profilée » : DataVision peut définir un contrat, le tester à chaque nouvelle version, tracer ses dépendances et empêcher la certification ou l'export d'un rapport si un contrat critique en mode `block` est rompu.

### Data Contracts exécutables

Les contrats supportent actuellement :

- colonnes requises ;
- volume minimum / maximum ;
- pourcentage maximal de valeurs manquantes ;
- unicité ;
- plages numériques ;
- valeurs autorisées ;
- type attendu ;
- regex ;
- dérive de distribution numérique par statistique KS ;
- dérive catégorielle par Total Variation Distance.

Chaque règle possède une sévérité et peut être bloquante. Le contrat possède un mode :

```text
monitor → mesure uniquement
warn    → signale sans bloquer
block   → interdit la publication/certification si une règle bloquante échoue
```

Le score de fiabilité est calculé par le moteur déterministe en pondérant les échecs selon leur sévérité.

### Contrôles automatiques sur les nouvelles versions

Lorsqu'une transformation gouvernée crée une nouvelle version immuable, les contrats actifs de la lignée sont réexécutés automatiquement. Les refresh SQL v2.7 exécutent également les contrats après matérialisation.

```text
Dataset v3
   ↓ transformation / refresh
Dataset v4
   ↓
Data Contracts
   ↓
healthy / warning / failing / critical
```

Le Data Reliability Gate exige aussi qu'un contrat en mode `block` ait été exécuté sur **la version exacte** qui doit être publiée. Un succès obtenu sur v3 ne suffit donc pas à autoriser automatiquement v4.

### Publication Gate

Le gate est réellement branché sur deux flux critiques :

- certification depuis le Review Center ;
- export PDF/DOCX/HTML/Markdown d'un rapport en contexte Enterprise.

Si un contrat critique en mode `block` échoue, l'opération est refusée avec le contrat responsable. Les modes `monitor` et `warn` restent visibles comme avertissements.

### Lineage de bout en bout

Le graphe consolide automatiquement les dépendances existantes :

```text
Source SQL
   ↓
Dataset v1 → Dataset v2 → Dataset v3
   ↓             ↓             ↓
Métrique       Analyse       Modèle
                                ↓
Dashboard                       ↓
   ↓                          Rapport
Rapport
```

Les nœuds disponibles incluent :

- sources externes ;
- versions de datasets ;
- analyses AI Analyst ;
- modèles ML ;
- métriques sémantiques ;
- dashboards ;
- rapports.

L'API peut calculer l'**impact downstream** d'un dataset ou d'une autre ressource avant modification.

### Reliability Center

L'interface v2.8 ajoute :

- scorecards de fiabilité ;
- état du Publication Gate ;
- créateur de Data Contract ;
- génération d'un contrat recommandé à partir du dataset actif ;
- détail des checks `pass/fail` ;
- incidents de fiabilité ;
- lineage visuel par colonnes Sources / Datasets / Consommateurs ;
- clic sur un nœud pour calculer l'analyse d'impact.

La zone **Gouverner** s'ouvre désormais par défaut sur Fiabilité & Lineage, avant Sources & Refresh et Gouvernance.

## Sécurité et gouvernance

La v2.8 conserve la boundary Enterprise introduite en v2.2 :

- organisations et workspaces ;
- RBAC ;
- RLS et sécurité colonne dans tout le pipeline analytique ;
- PostgreSQL comme metadata store principal avec fallback SQLite ;
- audit log ;
- worker Redis ;
- connecteurs PostgreSQL/MySQL avec credentials chiffrés ;
- refresh asynchrone tenant-aware ;
- reviews et certifications gouvernées.

Les Data Contracts sont évalués sur le data product du workspace, pas sur une vue RLS propre à un rôle individuel. Seuls les rôles autorisés peuvent créer ou exécuter les contrats.

### Permissions Reliability

| Rôle | Lire contrats / lineage | Créer / modifier contrats | Exécuter |
|---|---:|---:|---:|
| Owner | ✓ | ✓ | ✓ |
| Admin | ✓ | ✓ | ✓ |
| Data Scientist | ✓ | ✓ | ✓ |
| Analyst | ✓ | — | — |
| Viewer | ✓ | — | — |

## Validation v2.8.0

```text
Backend pytest                       : 50 passed
Python compileall                    : OK
TS/TSX syntax                        : OK
strictNullChecks ciblé               : OK
Data contracts                       : testé
Missing / uniqueness / range rules   : testé
Distribution drift KS + TVD          : testé
Reliability score                    : testé
Publication gate                     : testé
Certification blocking               : testé
Report export blocking               : testé
Lineage graph                        : testé
Impact analysis                      : testé
Tenant-aware workspace isolation     : conservé
Ports                                : 3005 / 8005
```

Le build Docker/Next complet reste à confirmer sur la machine cible avant validation frontend de production. Les tests réseau PostgreSQL/MySQL réels nécessitent un serveur externe accessible.

## Installation Docker

```powershell
cp .env.example .env
docker compose build web
docker compose build api
docker compose up -d
docker compose ps
```

Ou sous Windows :

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-windows.ps1
```

Puis ouvrir :

```text
http://localhost:3005
```

## Documentation

Les documents principaux sont dans `docs/` :

- `DATA_RELIABILITY_LINEAGE_V280.md`
- `VALIDATION_V280.md`
- `CONNECTORS_REFRESH_V270.md`
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
- gouvernance appliquée au pipeline analytique complet ;
- un contrat critique ne peut pas être contourné par un export Enterprise ;
- aucune fonctionnalité fictive présentée comme implémentée ;
- décisions humaines documentées avant certification des actifs analytiques.
