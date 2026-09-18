# DataVision AI — v2.10.0

DataVision AI est un **Data Intelligence Workspace local, installable, gouverné et collaboratif** couvrant le cycle : connecter → versionner → contrôler → analyser → modéliser → expliquer → décider → publier → revoir.

## Ports

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

Les ports 3000 et 8000 ne sont pas utilisés.

## Nouveau dans v2.10.0 — Governed Actions & Automation

La zone **Décider → Actions & Automation** transforme les insights en actions externes contrôlées. DataVision ne passe jamais directement d'une détection à un effet externe sans appliquer les règles du workspace.

### Pipeline d'action gouverné

```text
Signal / événement
      ↓
Règle + conditions
      ↓
Dedupe / throttling / quiet hours
      ↓
Approbation humaine si requise
      ↓
Webhook HTTPS signé HMAC
      ↓
Delivery audit + retry/backoff + replay
```

Les événements natifs supportés sont `proactive_alert`, `reliability_failure`, `review_approved`, `certification_created` et `manual`. Les règles peuvent être liées à un dataset précis et filtrer les événements par conditions déterministes (`eq`, `neq`, `contains`, `in`, comparaisons numériques, `exists`).

### Human-in-the-loop

Trois politiques sont disponibles : `always`, `critical_only` et `none`. Une action en `pending_approval` ne peut pas être exécutée par le worker. Owner/Admin/Data Scientist peuvent approuver ou rejeter selon RBAC ; les Analysts peuvent déclencher les événements autorisés mais pas approuver.

### Sécurité de livraison

- HTTPS obligatoire hors localhost en développement ;
- blocage DNS/IP des destinations privées, loopback, link-local, réservées ou multicast ;
- secret webhook chiffré au repos avec la même enveloppe que les credentials connecteurs ;
- signature `X-DataVision-Signature: v1=<HMAC-SHA256>` ;
- timestamp signé et `Idempotency-Key` stable ;
- headers sensibles protégés contre l'écrasement ;
- payload métier templatable sans exposer automatiquement les données brutes.

### Contrôle du bruit et des effets

Chaque règle peut définir une fenêtre de déduplication, un throttling, des quiet hours avec timezone IANA, ainsi qu'une politique de retry/backoff. Les quiet hours créent une action `scheduled`; le worker la remet en file lorsqu'elle devient exécutable. Un replay manuel crée une nouvelle exécution liée à l'originale, avec un fingerprint distinct et un audit explicite.

### Déclenchements natifs

- une alerte de l'Inbox proactive peut déclencher une règle `proactive_alert` en mode Enterprise ;
- un Data Contract en échec émet `reliability_failure` ;
- une revue approuvée émet `review_approved` ;
- une certification émet `certification_created`.

La règle essentielle reste : **DataVision peut recommander et préparer une action, mais les politiques d'approbation du workspace gardent le contrôle de l'effet externe.**

## Nouveau dans v2.9.0 — Observability, Evaluation & Operational Intelligence

La zone **Gouverner → Observabilité & Eval** ajoute un cockpit opérationnel pour mesurer ce qui fonctionne réellement, ce qui est utilisé, et si l’AI Analyst reste stable dans le temps.

### Observabilité structurée

DataVision enregistre désormais, en best-effort et sans bloquer les requêtes :

- latence des appels HTTP ;
- statut HTTP ;
- feature concernée ;
- utilisateur/workspace lorsque le contexte Enterprise existe ;
- exécutions de jobs et tentatives ;
- runs d’évaluation AI Analyst ;
- tokens/coûts lorsqu’un fournisseur LLM instrumenté les rapporte.

Le dashboard opérationnel calcule p50/p95/p99, disponibilité API, taux de succès des jobs, taux de succès des refresh et principaux modules utilisés.

### SLO explicites

Le cockpit expose actuellement quatre SLO opérationnels par fenêtre temporelle : disponibilité API, p95 de latence API, succès des jobs et succès des refresh. Les seuils sont affichés avec leur état `met/not met` ; ils ne sont pas présentés comme une certification externe.

### Usage Analytics

Les requêtes sont classées par domaine fonctionnel afin de distinguer les modules réellement utilisés : Data Workspace, SQL, AutoML, AI Analyst, Semantic Layer, Dashboards, Reports, Reliability, Connectors, Review Center, etc. Cela permet de piloter la roadmap à partir de l’usage réel plutôt que d’hypothèses.

### AI Analyst Evaluation Lab

Une suite d’évaluation peut être liée à un dataset gouverné et contenir des cas avec attentes vérifiables :

- intent attendu ;
- outils obligatoires ;
- statut Critic ;
- termes devant apparaître dans la réponse ;
- nombre minimal de findings ;
- durée maximale ;
- valeur attendue sur un chemin de résultat avec tolérance.

Chaque run conserve score, checks, durée et snapshot compact. Le moteur d’évaluation réutilise le même contexte RBAC/RLS/Column Security que les analyses normales.

### Retry / backoff des jobs

Les jobs Redis possèdent maintenant une politique de retry configurable (`0..5`) et un backoff exponentiel. Les retries attendent dans un sorted set Redis et ne bloquent pas le worker. Chaque tentative est enregistrée séparément avec son statut, sa latence et l’erreur éventuelle. L’écran Gouvernance expose aussi les deux réglages lors de la mise en file d’un job : nombre maximal de retries et backoff initial en secondes.

### Limite volontaire

Les colonnes `input_tokens`, `output_tokens` et `estimated_cost_usd` sont prêtes et le cockpit les affiche, mais DataVision **n’invente jamais** de coût lorsqu’aucun fournisseur LLM instrumenté ne le remonte. L’instrumentation provider-native reste donc partielle tant qu’un provider externe n’est pas branché.

## Héritage v2.8.0 — Data Reliability & Lineage

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

## Validation v2.10.0

```text
Backend pytest                       : 55 passed
Python compileall                    : OK
TS/TSX syntax                        : OK
strictNullChecks ciblé               : OK
Governed action lifecycle            : testé
Human approval / rejection           : testé
Signed HMAC webhook                  : testé
Delivery attempt audit               : testé
Deduplication                        : testé
Throttling / quiet hours             : testé
Replay                               : testé
RBAC Actions                         : testé
Internal action job guard            : testé
Native event dispatch                : intégré
Ports                                : 3005 / 8005
```

Le build Docker/Next complet reste à confirmer sur la machine cible avant validation frontend de production. Les livraisons vers de vrais endpoints Internet ne sont pas revendiquées comme validées dans l'environnement de génération.

## Validation v2.9.0

```text
Backend pytest                       : 52 passed
Python compileall                    : OK
TS/TSX syntax                        : OK
strictNullChecks ciblé               : OK
Operational telemetry                : testé
Feature usage analytics              : testé
AI evaluation suites                 : testé
Job retry/backoff                    : testé
Job attempt tracking                 : testé
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

- `OPERATIONAL_INTELLIGENCE_V290.md`
- `VALIDATION_V290.md`
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
