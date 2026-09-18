# DataVision AI — v2.12.0

DataVision AI est un **Data Intelligence Workspace local, installable, gouverné et collaboratif** couvrant le cycle : connecter → versionner → contrôler → analyser → modéliser → expliquer → décider → publier → revoir.

## Ports

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

Les ports 3000 et 8000 ne sont pas utilisés.

## Nouveau dans v2.12.0 — Identity, SSO & Secret Management

La zone **Gouverner → Identité & Secrets** ajoute une couche d'identité Enterprise complète au-dessus de l'authentification locale existante : sessions persistantes révocables, refresh tokens rotatifs, SSO OIDC Authorization Code + PKCE, provisioning JIT et coffre de secrets versionné.

### Sessions persistantes et refresh rotation

```text
Login / SSO
   ↓
Session serveur
   ├── access token court
   └── refresh token rotatif
            ↓
          refresh
            ↓
ancien refresh invalidé + nouveau refresh émis
```

Le refresh token brut n'est jamais stocké. Seul son hash est conservé dans `auth_sessions`. Les access tokens v2.12 portent un identifiant de session et sont refusés dès que la session est révoquée. L'utilisateur peut voir ses sessions, en fermer une ou fermer toutes les autres sessions.

### SSO OIDC moderne

Les Owner/Admin peuvent configurer un fournisseur OIDC par workspace. Le flux v2.12 supporte discovery, Authorization Code, PKCE S256, state/nonce, JWKS, validation cryptographique RS256, restrictions de domaines email, provisioning JIT et mapping durable de l'identité externe.

```text
DataVision → IdP → authorization code → token endpoint
                     ↓
                ID token RS256
                     ↓
              JWKS + iss/aud/exp/nonce
                     ↓
              session DataVision
```

Le client secret OIDC reste chiffré au repos. Les fournisseurs actifs sont proposés directement sur l'écran de connexion Enterprise.

### Secret Vault versionné

Le coffre de secrets supporte trois backends :

- `local_encrypted` pour un secret chiffré par DataVision ;
- `env` pour référencer une variable d'environnement ;
- `vault_kv2` pour résoudre un champ depuis HashiCorp Vault KV v2.

Une rotation crée une nouvelle version et retire l'ancienne. Les valeurs, ciphertexts et tokens externes ne sont jamais renvoyés par les APIs de lecture.

### Sécurité réseau

Les appels externes OIDC/Vault exigent HTTPS hors développement et appliquent une garde SSRF : credentials dans URL, loopback, réseaux privés, link-local, multicast et plages réservées sont refusés.

### Limites explicites

La v2.12 ne revendique pas encore SCIM, MFA/WebAuthn, KMS/HSM externe ni routage automatique des IdP par domaine. Le support ID token est volontairement limité à RS256. Le `next build` Docker complet et les connexions à un IdP/Vault réels restent à valider dans l'environnement cible.

## Validation v2.12.0

```text
Backend pytest                       : 64 passed
Python compileall                    : OK
TS/TSX syntax                        : OK
strictNullChecks ciblé               : OK
Persistent sessions                  : testé
Refresh token rotation               : testé
Server-side revocation               : testé
OIDC PKCE + one-time state            : testé
RS256/JWKS verification               : testé
OIDC JIT provisioning                 : testé
Versioned secret vault                : testé
Environment secret references         : testé
HashiCorp Vault KV v2 adapter         : testé
Ports                                : 3005 / 8005
```

La documentation détaillée est dans `docs/IDENTITY_SSO_SECRETS_V2120.md` et `docs/VALIDATION_V2120.md`.

## Nouveau dans v2.11.0 — Enterprise Action Connectors

La zone **Décider → Actions & Automation** devient un véritable hub d'intégration gouverné. Les règles v2.10 sont conservées, mais les destinations peuvent maintenant être des connecteurs natifs **Slack, Microsoft Teams, Jira, Email SMTP** ou un webhook générique.

### Connecteurs natifs

```text
Insight / événement
      ↓
Règle déterministe
      ↓
Policy d'approbation
      ↓
┌────────┬─────────┬──────┬───────┬─────────┐
│ Slack  │ Teams   │ Jira │ Email │ Webhook │
└────────┴─────────┴──────┴───────┴─────────┘
      ↓
Delivery audit + retry/backoff + replay
```

Les adaptateurs actuellement implémentés sont :

- Slack Incoming Webhook ;
- Slack Web API `chat.postMessage` avec Bearer/OAuth2 client credentials ;
- Microsoft Teams Workflow/Webhook ;
- Jira Cloud `POST /rest/api/3/issue` ;
- SMTP / SMTP STARTTLS / SMTP SSL ;
- webhook HTTPS générique signé HMAC.

### Credential vault gouverné

Les credentials sont stockés chiffrés côté serveur et ne sont jamais renvoyés par l'API. Les profils supportent `bearer`, `basic`, `smtp` et `oauth2_client_credentials`. Les URL Slack/Teams/webhook contenant des secrets sont elles aussi chiffrées au lieu d'être exposées dans le catalogue des destinations. Les headers sensibles sont masqués.

Le flux OAuth2 des **connecteurs d’action v2.11** reste `client_credentials`. Le SSO interactif **OIDC Authorization Code + PKCE** est désormais implémenté séparément par la v2.12 pour l’identité utilisateur.

### Approbations multi-étapes

Une règle peut utiliser `approval_mode = chain` et définir jusqu'à six étapes ordonnées. Chaque étape cible un rôle ou un utilisateur précis.

```text
Action proposée
   ↓
1. Revue technique · data_scientist
   ↓
2. Validation administrative · admin
   ↓
Quiet hours / throttling
   ↓
Exécution externe
```

L'étape suivante ne peut pas être contournée par un approbateur ayant un autre rôle. Un rejet arrête la chaîne et marque les étapes restantes comme `skipped`. Le détail d'un run expose l'avancement étape par étape.

### Sécurité et contrôle opérationnel

La v2.11 conserve et renforce :

- RBAC workspace ;
- chiffrement des secrets ;
- HTTPS obligatoire hors localhost en développement ;
- garde SSRF pour les destinations HTTP ;
- HMAC + timestamp + idempotency key pour les webhooks génériques ;
- déduplication et throttling ;
- quiet hours timezone-aware ;
- retries exponentiels non bloquants via Redis ;
- audit des tentatives ;
- replay gouverné ;
- test explicite d'une destination par Owner/Admin.

### Limites explicites

Le package ne prétend pas valider une livraison réelle vers Slack/Teams/Jira/SMTP sans credentials et réseau externes disponibles. Les adaptateurs, payloads, contrôles RBAC, chiffrement et enchaînements sont testés localement avec doubles de transport. Le build Next.js complet reste à confirmer sur la machine Docker cible.

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

## Validation v2.11.0

```text
Backend pytest                       : 59 passed
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
