# DataVision AI — v2.22.0

DataVision AI est un **Data Intelligence Workspace local, installable, gouverné et collaboratif** couvrant le cycle : connecter → versionner → contrôler → analyser → modéliser → expliquer → décider → publier → revoir.


## Nouveau dans v2.15.3 — Assistant agentique cumulatif v2.13 → v2.15

Cette distribution est construite directement sur la base complète v2.12 et conserve
tous les modules historiques et Enterprise existants.

Les évolutions intermédiaires sont cumulées :

- **v2.13.0** : assistant flottant, texte/voix, Context Engine, Event Bus ;
- **v2.13.1** : Tool Registry, mémoire de session, Activity Monitor, executor gouverné ;
- **v2.13.2** : validation structurée des plans ;
- **v2.13.3** : Host Bridge, ActionRun, confirmation, realtime SSE ;
- **v2.13.4** : contrats métier Data/Stats/ML/GIS/Reporting/Fichiers ;
- **v2.14.0** : Agent Orchestrator, intent resolver, planner, Critic, recovery ;
- **v2.14.1** : séquencement strict et reprise après confirmation ;
- **v2.14.2** : liaison complète Floating UI ↔ Orchestrator ;
- **v2.15.0** : Model Gateway local/cloud avec politique de confidentialité ;
- **v2.15.3** : fusion réelle avec les moteurs et RBAC de DataVision v2.12.

Le LLM reste un planner/explainer : les calculs statistiques et ML proviennent
des moteurs déterministes de DataVision.


## Correction v2.15.4 — Assistant visible sans Tailwind

La base v2.12 n'utilise pas Tailwind CSS. Le composant flottant v2.15.3
employait encore des classes utilitaires Tailwind, qui n'étaient donc pas
appliquées.

La v2.15.4 remplace entièrement ce styling par un CSS Module natif Next.js :

- bouton `DV AI` réellement fixé en bas à droite ;
- z-index élevé ;
- panneau conversationnel complet ;
- responsive mobile ;
- aucune dépendance Tailwind ;
- toutes les fonctions texte, voix, fichiers, plans et actions sont conservées.


## Correction v2.16.1 — Parole naturelle

Le moteur vocal ne lit plus les marqueurs visuels comme `(s)`, `(e)` ou `(es)`.

Les messages générés utilisent désormais une vraie flexion française :

```text
1 étape exécutée et validée
3 étapes exécutées et validées
```

Une couche `toSpeechText()` nettoie aussi le Markdown, les URLs et certains
séparateurs techniques avant synthèse vocale.



## Correction v2.16.2 — Compréhension conversationnelle et résultats

L'assistant ne transforme plus une question inconnue en analyse du dataset
simplement parce qu'un dataset est actif.

Exemples :

```text
« Où sont les résultats ? »
→ restitue les résultats du dernier TurnRun.

« Tu as accès à internet ? »
→ explique les capacités réseau réelles de DataVision.

Question non comprise
→ demande une clarification sans lancer de calcul.
```

Les analyses terminées exposent désormais directement leurs résultats
déterministes (lignes, variables, doublons, valeurs manquantes, métriques
disponibles) au lieu d'afficher uniquement le nombre d'étapes réussies.



## Nouveau dans v2.17.0 — AI Control Center & compréhension hybride

### Gouverner → IA & Modèles

DataVision dispose maintenant d'un Control Center natif pour :

- ajouter des providers locaux, on-premise ou OpenAI-compatibles ;
- tester leur connexion sans envoyer de dataset ;
- choisir le modèle utilisé pour Planner, Explication, Critic et Résumé ;
- définir un ordre de fallback ;
- appliquer `local_only`, `prefer_local` ou `allow_external` ;
- autoriser explicitement l'IA externe ;
- définir un budget mensuel ;
- suivre les tokens et coûts estimés ;
- référencer le Secret Vault Enterprise ou une variable d'environnement locale.

### Compréhension hybride

Le routeur déterministe reste prioritaire.

Si une question n'est pas comprise et que le Model Gateway est activé :

```text
question inconnue
    ↓
classification LLM structurée
    ↓
validation par liste fermée d'intentions
    ↓
planner / réponse explicative / clarification
```

Le modèle ne reçoit aucune capacité d'exécution directe.

### Contexte sémantique enrichi

L'assistant connaît maintenant le schéma du dataset :

```text
nom de colonne + type
```

sans transmettre les lignes ou valeurs brutes.

Les noms de colonnes peuvent être masqués pour les providers externes.



## Nouveau dans v2.18.0 — Notebook sandboxé Python / SQL / R

La zone **Analyser → Notebook** ajoute un workspace reproductible multi-cellules.

### Langages

- Python ;
- SQL read-only ;
- R ;
- Markdown.

### Isolation

Python et R ne s'exécutent jamais dans le processus FastAPI principal.

```text
Frontend
  ↓
Notebook API
  ↓
dataset gouverné par RBAC/RLS
  ↓
service sandbox privé
  ├── utilisateur non-root
  ├── filesystem read-only
  ├── tmpfs
  ├── cap_drop ALL
  ├── no-new-privileges
  ├── limite CPU / mémoire / PID
  ├── timeout par cellule
  └── réseau Docker internal-only
```

Le service sandbox n'expose aucun port sur l'hôte.

### Reproductibilité

Chaque run conserve :

- notebook ;
- cellule ;
- source hashée ;
- langage ;
- dataset ;
- version du dataset ;
- moteur ;
- stdout / stderr ;
- résultat structuré ;
- artefacts ;
- temps d'exécution ;
- timestamp ;
- provenance.

### SQL

Les cellules SQL réutilisent le SQL Workspace DataVision existant :

- `SELECT` / `WITH` uniquement ;
- DuckDB préféré ;
- aucune mutation ;
- table gouvernée `dataset`.

### Agent

L'assistant connaît désormais les notebooks et peut proposer
`execute_notebook_cell`.

Cette action exige toujours une **confirmation humaine**, même si la cellule
est exécutée dans le sandbox.



## Correction v2.18.1 — Assistant plus naturel et contrôle vocal

### Synthèse vocale

La synthèse vocale est désormais :
- désactivée par défaut ;
- activable/désactivable indépendamment du microphone ;
- persistée dans le navigateur ;
- immédiatement interrompue lorsqu'elle est désactivée.

`Conversation continue` concerne uniquement l'écoute vocale. Elle ne force plus
DataVision à lire toutes ses réponses.

### Compréhension sans LLM obligatoire

Un dataset actif expose maintenant au Context Engine :
- nom ;
- nombre de lignes ;
- nombre de variables ;
- score qualité ;
- nombre de problèmes qualité ;
- cellules manquantes ;
- doublons ;
- nombre de variables numériques/catégorielles ;
- schéma des colonnes.

Ainsi une question naturelle comme :

```text
Comment tu trouves le dataset ?
```

reçoit une appréciation factuelle immédiate, même si aucun provider LLM n'est
configuré.

Le Model Gateway reste utilisé pour les formulations plus complexes, mais il
n'est plus nécessaire pour les questions courantes sur le dataset.



## Nouveau dans v2.18.2 — Mémoire conversationnelle courte

L'assistant conserve désormais une mémoire sémantique compacte de la session :

- dernière intention ;
- dernières entités analytiques ;
- variables récemment focalisées ;
- dernier résumé de résultat ;
- décisions exécutées.

Il ne conserve pas une copie brute illimitée de la conversation.

Exemples pris en charge :

```text
« fais un graphique de Sales »
« fais pareil avec Profit »
```

```text
« comment tu trouves le dataset ? »
« et pourquoi ? »
```

```text
« montre-moi ça en graphique »
```

Les références ambiguës ne sont pas devinées :

```text
« compare-le avec l'autre »
```

Si deux variables récentes ne permettent pas de résoudre précisément
« l'autre », DataVision demande la deuxième variable.

Le contexte de session reste stable dans le navigateur via
`sessionStorage`, ce qui permet aux relances successives de partager la même
mémoire courte.



## Nouveau dans v2.19.0 — XAI avancé & Model Benchmark

### Benchmark multi-moteurs

DataVision peut désormais comparer, selon disponibilité runtime :

- Régression logistique / linéaire / Ridge ;
- Random Forest ;
- Extra Trees ;
- Gradient Boosting ;
- Histogram Gradient Boosting ;
- SVM ;
- XGBoost ;
- LightGBM ;
- CatBoost.

Le benchmark :
- utilise uniquement le sous-ensemble d'entraînement pour la cross-validation ;
- classe les candidats sur le jeu de validation ;
- conserve le test final hors sélection ;
- n'échoue pas globalement si un moteur optionnel est indisponible ;
- expose le statut et l'erreur de chaque candidat.

### XAI complet

Le module **Modéliser → XAI** ajoute :

- permutation importance ;
- SHAP global et local lorsque le pipeline est compatible ;
- dépendance partielle (PDP) ;
- calibration binaire ;
- Expected Calibration Error (ECE) ;
- matrice de confusion ;
- ROC / Precision-Recall ;
- diagnostics de résidus ;
- recherche contrefactuelle bornée ;
- explication locale par perturbation.

Aucune de ces sorties n'est présentée comme une preuve causale.

### Assistant

Le Tool Registry ajoute `benchmark_models`.

`explain_model` peut maintenant demander :
- `diagnostics` ;
- `shap_global` / `shap_local` ;
- `partial_dependence` ;
- `counterfactuals`.

Tous les calculs passent par les moteurs déterministes DataVision.



## Nouveau dans v2.20.0 — Root Cause Analysis & Decision Intelligence

### Root Cause Analysis déterministe

Le **Decision Lab** ne dépend plus obligatoirement d'un modèle.

À partir d'un dataset actif, DataVision peut maintenant comparer deux groupes
ou deux périodes et décomposer l'écart d'un indicateur numérique.

Métriques :
- moyenne ;
- somme ;
- nombre de valeurs.

Pour chaque dimension explicative, le moteur calcule :
- taille baseline / actuelle ;
- moyenne baseline / actuelle ;
- contribution nette ;
- effet de composition (`mix_effect`) ;
- effet de niveau (`rate_effect`) pour une moyenne ;
- erreur de réconciliation.

Pour les moyennes, la décomposition symétrique réconcilie exactement l'écart
global lorsque tous les segments sont inclus.

### Comparaison temporelle

Une variable de date peut être regroupée automatiquement par :
- jour ;
- semaine ;
- mois ;
- trimestre ;
- année.

En mode `auto`, DataVision choisit une granularité cohérente avec la durée de
la série.

### Distribution Shift

Le RCA compare également les distributions entre baseline et période actuelle :

- variable numérique : déplacement standardisé ;
- variable catégorielle : Total Variation Distance (TVD).

Ces signaux servent à prioriser les variables à examiner, jamais à déclarer
une causalité.

### Priorités de revue

Le moteur produit une liste de `review_priorities` fondée sur :
- contributions segmentaires ;
- changements de distribution ;
- taille des groupes.

Le niveau `evidence_strength` est uniquement descriptif et n'est pas un score
de causalité.

### Optimisation multi-scénarios

Lorsqu'un modèle actif existe, le Decision Lab peut explorer un espace borné
de variables contrôlables :

```text
base_row
+ controls
+ objectif
        ↓
grid search borné
        ↓
modèle sauvegardé
        ↓
scénarios classés
```

Limites :
- 5 variables contrôlables maximum ;
- 5 000 scénarios maximum ;
- résultats classés par objectif puis coût de changement.

Objectifs régression :
- maximiser ;
- minimiser ;
- atteindre une valeur cible.

Pour une classification, DataVision classe les scénarios selon la probabilité
de la classe cible.

### AI Analyst

Les demandes comme :

```text
Pourquoi le chiffre d'affaires a baissé ?
Analyse les causes.
```

sont maintenant routées vers le moteur Root Cause plutôt que vers une simple
régression.

Le calcul reste effectué par le moteur déterministe ; le LLM n'invente aucune
contribution.

### Assistant flottant

Nouveaux tools gouvernés :
- `run_root_cause_analysis` ;
- `optimize_decision_scenarios`.

Ils passent par le Tool Registry, le RBAC/RLS et les moteurs DataVision.



## Nouveau dans v2.21.0 — Connecteurs avancés & Cloud Warehouses

Le centre **Données → Sources & Refresh** couvre maintenant onze familles de
connecteurs gouvernés :

- PostgreSQL ;
- MySQL ;
- MariaDB ;
- SQLite ;
- Microsoft SQL Server ;
- Oracle Database ;
- MongoDB ;
- Google BigQuery ;
- Snowflake ;
- Databricks SQL ;
- Amazon Redshift.

### Même pipeline de gouvernance

Tous les connecteurs réutilisent les briques existantes :

```text
Connector
  ↓
test / discovery
  ↓
source gouvernée
  ↓
preview read-only
  ↓
refresh full / incremental selon capacité
  ↓
nouvelle version immuable du dataset
  ↓
schema drift / freshness SLA / lineage / audit
```

Il n'existe pas de pipeline cloud séparé.

### Secrets

Le champ secret du connecteur est chiffré par DataVision avant stockage.

Les `options` restent non secrètes.

Exemples :
- Snowflake : `warehouse`, `schema`, `role` dans les options ;
- Databricks : `http_path`, `catalog`, `schema` dans les options et token dans
  le champ secret ;
- BigQuery : `project_id` dans Base/Projet, dataset/location dans les options,
  JSON de service account dans le champ secret ou secret vide pour ADC ;
- MongoDB : `auth_source`, `replica_set`, `tls` dans les options.

### SQLite

SQLite est volontairement confiné à :

```text
DATA_ROOT/connectors/sqlite
```

Une connexion ne peut pas pointer vers un fichier arbitraire du serveur.

### Runtime Catalog

Nouvel endpoint :

```text
GET /api/v1/workspaces/{workspace_id}/connectors/catalog
```

Il expose :
- types supportés ;
- port par défaut ;
- champs requis ;
- options non secrètes ;
- capacités de refresh ;
- disponibilité réelle du driver.

Un driver absent est signalé par :

```text
driver_missing
```

DataVision ne simule jamais une connexion réussie.

### MongoDB

MongoDB utilise des sources `collection` au lieu de requêtes SQL.

Les documents sont normalisés en dataframe lors du preview/refresh. Les types
BSON spéciaux comme ObjectId sont sérialisés de façon contrôlée.

### Assistant

Le Tool Registry expose aussi :

- `list_data_connectors` ;
- `discover_data_connector` ;
- `test_data_connector`.

Le test actif d'un système externe est classé `external` et nécessite donc la
confirmation prévue par la Safety Policy de l'assistant.



## Nouveau dans v2.22.0 — Plugin System & MCP

DataVision dispose désormais d'un registre d'extensions gouverné dans
**Gouverner → Plugins & MCP**.

Deux protocoles sont pris en charge :

- `mcp_http` : serveur MCP accessible par HTTP/HTTPS, avec `initialize`,
  `tools/list` et `tools/call` ;
- `http_json` : manifest déclaratif DataVision associant chaque tool à une
  méthode GET/POST et un chemin HTTP.

### Aucun code plugin arbitraire dans le cœur

La v2.22 ne charge pas de module Python tiers dans le processus FastAPI.
Les extensions sont des capacités distantes déclaratives. Elles doivent passer
par le même pipeline que les tools natifs :

```text
manifest / MCP tools/list
        ↓
validation JSON Schema
        ↓
Tool Registry DataVision
        ↓
RBAC workspace
        ↓
Safety Policy
        ↓
confirmation humaine
        ↓
appel externe borné
        ↓
audit / plugin_runs
```

### Risque canonique

Un plugin peut déclarer son propre risque à titre documentaire, mais DataVision
ne lui fait pas confiance pour abaisser son niveau de sécurité.

Tout tool distant est enregistré avec :

```text
risk = external
```

La confirmation humaine est donc obligatoire avant exécution par l'assistant.

### Isolation tenant-aware

Les tools importés sont isolés par workspace. Leur nom runtime contient un
suffixe dérivé du workspace et le catalogue présenté au planner est filtré par
contexte tenant.

Un tool d'un autre workspace est refusé même si son nom est fourni directement.

### Secret Vault

Les manifests n'acceptent pas de password, token, API key ou Authorization
bruts. Ils référencent uniquement `secret_id`.

Authentification supportée :

- aucune ;
- Bearer token via Secret Vault ;
- API key via un header autorisé et Secret Vault.

### Politique réseau

Les plugins publics exigent HTTPS et bloquent les destinations privées,
loopback, link-local et metadata endpoints.

Les plugins `network_scope=private` peuvent atteindre un intranet explicitement
configuré, mais loopback/link-local restent bloqués.

Les query strings et credentials dans l'URL sont interdits.

### Contexte transmis

Par défaut :

```text
context_policy = none
```

Aucun contexte DataVision n'est alors joint automatiquement.

Avec `semantic`, seuls des identifiants et éléments sémantiques minimaux peuvent
être joints : workspace, route, dataset/model IDs et objet sélectionné. Les
lignes brutes du dataset et `uiState` ne sont jamais ajoutés automatiquement.

### Bornes d'exécution

- manifest : 256 Ko maximum ;
- 100 tools maximum par plugin ;
- JSON Schema : 64 Ko maximum par tool ;
- requête distante : 256 Ko maximum ;
- réponse distante : 2 Mo maximum, lue en streaming ;
- timeout : 2 à 30 secondes ;
- aucun redirect HTTP automatique.

### Audit

DataVision conserve :

- plugin installé / mis à jour / supprimé ;
- synchronisation MCP ;
- test de plugin ;
- tool exécuté ;
- statut, durée et noms des clés d'arguments.

Les valeurs complètes des arguments ne sont pas persistées dans `plugin_runs`.

### MCP

La v2.22 fournit une compatibilité MCP HTTP avec réponses JSON et lecture
bornée des réponses `text/event-stream` simples. Le protocole de compatibilité
par défaut est configurable dans le manifest (`protocol_version`).

Cette version ne revendique pas encore : marketplace public, signatures de
packages, MCP stdio local, OAuth dynamique MCP, sampling MCP, resources/prompts
MCP ni exécution de code plugin local.

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
