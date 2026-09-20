# DataVision AI — v2.44.0

DataVision AI est un **Data Intelligence Workspace local, installable, gouverné et collaboratif** couvrant le cycle : connecter → versionner → contrôler → analyser → modéliser → expliquer → décider → publier → revoir.


## Nouveau dans v2.44.0 — Assistant V1 réellement tool-connected

La v2.44.0 ferme le lot **Assistant V1** en s'appuyant sur l'architecture agentique déjà présente, sans créer un second chatbot parallèle :

- assistant flottant monté globalement dans l'application ;
- contexte live écran / workspace / dataset / version / modèle lu au moment exact de chaque tour et action ;
- catalogue et planner limités aux outils réellement raccordés à un handler DataVision ;
- refus déterministe des outils déclarés mais non disponibles dans le runtime ;
- exécution via les moteurs DataVision réels et leurs permissions RBAC ;
- confirmations humaines conservées pour les actions gouvernées ;
- resynchronisation automatique de l'interface après transformation de dataset, création de modèle, rapport ou visualisation ;
- upload de fichiers, texte, écoute et synthèse vocale conservés ;
- gate exécutable `python scripts/assistant_acceptance.py --root . --check` ;
- manifest de preuve `compliance/ASSISTANT_ACCEPTANCE.json`.

Aucun volume Docker ni dataset existant n'a besoin d'être supprimé pour passer de v2.43.0 à v2.44.0.


## Nouveau dans v2.43.0 — Data Workspace reproductible

La v2.43.0 transforme le notebook existant en **Data Workspace relié aux versions immuables du dataset** :

- SQL local strictement read-only via DuckDB/SQLite fallback ;
- Python et R exécutés dans le sandbox interne isolé ;
- notebooks visibles sur toute la lignée d'un dataset ;
- rebinding explicite vers une version précise ;
- exécution ordonnée de toutes les cellules avec arrêt contrôlé sur erreur ;
- provenance de run enrichie : version, root, lignée, dimensions, hash du code et fingerprint SHA-256 des données ;
- artefacts persistés et téléchargeables ;
- promotion contrôlée d'un artefact CSV/JSON en nouvelle version gouvernée du dataset ;
- gate exécutable `python scripts/workspace_acceptance.py --root . --check` ;
- manifest de preuve `compliance/WORKSPACE_ACCEPTANCE.json`.

Aucun volume Docker n'a besoin d'être supprimé pour passer de v2.42.0 à v2.43.0. Les notebooks historiques restent compatibles.


## Nouveau dans v2.42.0 — Data Preparation Completion

La v2.42.0 ferme le lot **Data Preparation** avec des transformations déterministes, versionnées et réellement rejouables :

- jointures multi-clés et concaténations lignes/colonnes ;
- GroupBy avec plusieurs agrégations ;
- pivot / unpivot ;
- feature engineering avancé : binning, lag et rolling ;
- pipelines multi-datasets avec dépendances et bindings de remplacement ;
- validation en mémoire de l'intégralité du pipeline avant persistance ;
- gate exécutable `python scripts/preparation_acceptance.py --root . --check` ;
- manifest de preuve `compliance/PREPARATION_ACCEPTANCE.json`.

Les pipelines historiques restent compatibles. Aucun volume Docker ni dataset existant n'a besoin d'être supprimé pour passer de v2.41.0 à v2.42.0.


## Nouveau dans v2.41.0 — MVP Acceptance exécutable

La v2.41.0 transforme le MVP en **workflow vérifiable**, et non plus en simple présence de modules. Le gate couvre explicitement les 16 exigences obligatoires et exécute le parcours prioritaire `import → profiling → quality → preparation → statistics → visualization → history → export`.

- nouvelle matrice `compliance/MVP_ACCEPTANCE.json` ;
- nouveau gate `python scripts/mvp_acceptance.py --root . --check` ;
- test backend intégré de l’API publique ;
- E2E Docker via le proxy same-origin `/api/backend` ;
- correction P0 de l’import JSON : les données restent dans `<id>.json` et les métadonnées utilisent désormais `<id>.meta.json` ;
- compatibilité de lecture conservée pour les anciens sidecars metadata valides ;
- les anciens uploads JSON déjà écrasés avant v2.41.0 doivent être réimportés depuis leur source.



## Correctif v2.40.4 — Feature Store strict typing

La v2.40.4 corrige le blocage TypeScript observé pendant le build Docker/Next de la v2.40.3 dans `FeatureServingView.tsx`.

- la collection `columns` issue du dataset actif est explicitement normalisée en `AnyObj[]` ;
- `columnNames` est explicitement typé `string[]` ;
- les trois callbacks `columnNames.map(...)` utilisent un paramètre `name: string`, supprimant toute inférence implicite `any` ;
- ajout d’un test de non-régression dédié au Feature Store ;
- aucun changement des contrats API, des données persistées ou des moteurs statistiques/ML.

Le build Docker/Next complet reste à confirmer sur la machine cible ; les avertissements Autoprefixer restent non bloquants.


## Correctif v2.40.3 — Null-safety frontend consolidée

La v2.40.3 corrige le blocage TypeScript suivant observé pendant le build Docker/Next de la v2.40.2 et consolide les mêmes risques dans les autres vues concernées.

- le formulaire **Sources & Refresh** capture désormais `connectorSpec?.options` dans `connectorOptions` avant le JSX, évitant tout accès direct à un connecteur potentiellement nul ;
- `ComplianceCenter` capture la liste `signoff_required` dans une référence non nulle avant le rendu ;
- `ResponsibleAIView` capture le modèle sélectionné dans `activeModel` avant les callbacks asynchrones d’audit, de risque, de publication et de drift ;
- ajout de tests de non-régression dédiés à ces trois gardes de nullabilité ;
- aucune modification des contrats API, des schémas de données ou des moteurs statistiques/ML.

Les avertissements Autoprefixer restent non bloquants et sont indépendants de ces erreurs TypeScript.

## Correctif v2.40.2 — Typage strict du payload contre-factuel

La v2.40.2 corrige le second blocage TypeScript observé pendant le build Docker/Next de la v2.40.1 : le payload transmis à `runModelCounterfactuals()` était typé comme `AnyObj`, ce qui ne garantissait pas la présence de la propriété obligatoire `row`. Le payload est désormais dérivé directement de la signature de l’API avec `Parameters<typeof runModelCounterfactuals>[1]`, et la ligne JSON est explicitement typée `Record<string, unknown>`.

## Correctif v2.40.1 — Build frontend / XAI

La v2.40.1 corrige le blocage TypeScript observé pendant le build Docker/Next de la v2.40.0 dans `XaiView.runCf()`.

- capture explicite du modèle non nul via `activeModel` après la garde de rendu ;
- les callbacks XAI (`diagnostics`, explication locale, SHAP, PDP et contre-factuels) utilisent cette référence stable ;
- suppression de l'accès non protégé `model.task` qui faisait échouer `next build` avec `model is possibly null` ;
- ajout d'un test de non-régression frontend ciblé ;
- aucune modification des contrats API, schémas de données ou moteurs statistiques/ML.

Les avertissements Autoprefixer observés pendant le build restent non bloquants et sont distincts de cette erreur TypeScript.

## Nouveau dans v2.40.0 — Production Baseline & Release Integrity

La v2.40.0 transforme la v2.39.1 stabilisée en **baseline de production vérifiable**.

- ajout de `scripts/production_baseline.py`, contrôle structurel sans dépendance réseau ;
- validation explicite de `VERSION`, des dépendances critiques, du proxy API same-origin, de `compliance/` et de l'adapter assistant ;
- le préflight Windows exécute désormais ce baseline avant tout build Docker ;
- `scripts/verify_release.py` vérifie maintenant le manifest embarqué, la liste exacte des fichiers, leurs tailles et leurs SHA-256 ;
- les chemins dangereux, doublons ZIP et fichiers non déclarés sont rejetés ;
- `scripts/release.py` auto-vérifie le ZIP produit avant de déclarer la release terminée ;
- ajout de tests de non-régression dédiés à l'intégrité des releases v2.40.0.

Cette version n'invente pas une validation Docker lorsqu'elle n'a pas été exécutée : les builds Docker/Next restent validés par la CI et par le préflight sur la machine cible.

## Correctif v2.39.1 — Gouverner / CDC & Acceptance

Le centre **Gouverner → CDC & Acceptance** est corrigé pour fonctionner dans la
distribution Docker, et non uniquement depuis l'arborescence source.

- `compliance/` est réellement embarqué dans l'image API ;
- le service CDC résout explicitement la racine `/app` dans Docker ;
- les appels frontend passent désormais par le proxy same-origin `/api/backend` ;
- le navigateur n'a plus à joindre directement `localhost:8005` pour les appels applicatifs ;
- l'écran CDC affiche une erreur exploitable et un bouton **Réessayer** si l'API est indisponible ;
- le préflight Windows vérifie la présence du correctif avant reconstruction.

## Nouveau dans v2.39.0 — Repository Cleanup & Professional Structure

La racine du dépôt est désormais limitée aux fichiers opérationnels réellement
utiles au lancement, au build, à la sécurité et à la documentation principale.

- `MERGE_MANIFEST_V*.json` → `docs/history/manifests/` ;
- `MIGRATION_FROM_V212.md` → `docs/history/migrations/` ;
- ajout de `docs/PROJECT_STRUCTURE.md` ;
- ajout de `.gitignore` et `.editorconfig` ;
- ajout de `scripts/repository_hygiene.py` ;
- contrôle d'hygiène exécuté par le préflight Windows et la CI.

Aucun moteur analytique, endpoint métier, composant de sécurité ou mécanisme du
Context Engine n'est supprimé par cette réorganisation.


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


## Nouveau dans v2.23.0 — Responsible AI & Fairness

La zone **Modéliser → Responsible AI** ajoute une couche de gouvernance des
modèles qui reste distincte du moteur prédictif.

### Sélection explicite des groupes

DataVision ne tente pas d'inférer automatiquement qu'une colonne représente
une caractéristique sensible. L'utilisateur choisit explicitement jusqu'à
3 variables de groupe à auditer.

Modes :

- audit séparé de chaque variable ;
- audit intersectionnel ;
- les deux simultanément.

L'évaluation utilise par défaut le **holdout final** sauvegardé avec le modèle.

### Classification

Lorsque la tâche est une classification, DataVision calcule par groupe :

- accuracy ;
- balanced accuracy ;
- F1 pondéré ;
- taux de sélection ;
- taux de vrais positifs ;
- taux de faux positifs ;
- précision sur la classe positive ;
- Brier score et calibration lorsque les probabilités sont disponibles.

Les synthèses incluent notamment :

- demographic parity difference ;
- selection rate ratio ;
- equal opportunity difference ;
- false positive rate difference ;
- equalized odds difference.

Aucune de ces métriques n'est interprétée comme définition universelle de
l'équité.

### Régression

Pour une régression, l'audit compare :

- MAE ;
- RMSE ;
- erreur moyenne ;
- R² ;
- ratios et écarts d'erreur entre groupes.

### Publication gate

Les seuils de blocage sont fournis par l'organisation. DataVision n'impose pas
un seuil de fairness par défaut.

Exemples de politiques possibles :

```json
{
  "max_demographic_parity_difference": 0.10,
  "min_selection_rate_ratio": 0.80,
  "max_equal_opportunity_difference": 0.10,
  "block_on_protected_feature_usage": true
}
```

Ces valeurs sont des **exemples de configuration**, pas des recommandations
universelles du produit.

Le résultat du gate peut être persisté dans la Model Card. Lorsqu'un modèle a
un gate Responsible AI enregistré comme bloqué, le Review Center refuse sa
certification tant que ce gate reste bloqué.

### Model Risk Assessment

DataVision agrège les signaux de gouvernance :

- taille du jeu de test ;
- garde-fous d'entraînement ;
- utilisation d'une variable d'audit comme feature ;
- groupes insuffisamment documentés ;
- présence ou absence d'une revue de performance par groupe.

Le niveau produit est un **risque de gouvernance du modèle**, jamais un jugement
sur une personne ou un groupe.

### Population drift

Un modèle peut être comparé à un dataset actif plus récent :

- dérive de représentation des groupes ;
- variation des parts de population ;
- nouvelle performance par groupe si la cible est disponible dans le dataset
  courant.

### Assistant

Nouveaux tools gouvernés :

- `evaluate_model_fairness` ;
- `assess_model_risk` ;
- `responsible_ai_publication_gate`.

Le calcul reste déterministe. L'assistant ne choisit pas lui-même les variables
sensibles à auditer.


## Nouveau dans v2.24.0 — Model Registry & MLOps

La zone **Modéliser → Model Registry** ajoute un cycle de vie persistant pour
les modèles DataVision.

### Lifecycle

```text
draft
  ↓
staging
  ↓
production
  ↓
retired
```

Un modèle en staging porte le rôle `challenger`. Un modèle promu en production
devient le `champion` de sa famille de modèles. Lorsqu'un nouveau champion est
promu, l'ancien champion est retiré automatiquement et l'événement est audité.

Une famille de modèles est définie par :

```text
dataset root + target + task
```

Chaque nouvel artefact reçoit un numéro de version Registry indépendant de
l'identifiant technique UUID du modèle.

### Intégrité des artefacts

Le Registry conserve :

- SHA256 du fichier `.joblib` ;
- SHA256 de la Model Card ;
- version Registry ;
- stage ;
- rôle ;
- horodatage des promotions/retraits ;
- historique des transitions.

Les enrichissements de gouvernance sont autorisés en draft/staging puis un
nouveau snapshot est pris avant la transition. Un changement de l'artefact de
production est ensuite détecté comme une violation d'intégrité.

### Gate de production

En Enterprise, une promotion `staging → production` exige :

- une certification active du modèle ;
- aucun Responsible AI Gate persisté comme bloqué.

Le Model Registry ne contourne donc pas le Review Center ni Responsible AI.

### Monitoring

Un run de monitoring compare le dataset d'entraînement au dataset courant :

```text
Model Card
   +
reference dataset
   +
current dataset
       ↓
performance actuelle
feature drift
       ↓
healthy / degraded
```

Pour les features numériques, DataVision mesure un déplacement standardisé.
Pour les features catégorielles, il calcule la Total Variation Distance.

Si la cible est disponible sur les données courantes, le moteur recalcule les
métriques du modèle et mesure la dégradation relative de la métrique primaire.

Les seuils de monitoring sont des paramètres opérationnels configurables et ne
sont pas présentés comme des seuils universels de qualité scientifique.

### Monitoring périodique

Le worker peut exécuter des jobs `model_monitor` selon un intervalle configuré.

Le scheduler :

- fonctionne avec un lock conditionnel en metadata store ;
- ne lance qu'un seul job pour une échéance donnée ;
- reste tenant-aware en Enterprise ;
- utilise le même moteur de monitoring que l'exécution manuelle.

Le monitoring périodique ne peut être activé qu'en `staging` ou `production`.

### Retraining Policy

Une politique de réentraînement peut définir :

- nombre minimum de lignes évaluées ;
- seuil de dégradation relative de performance ;
- seuil de feature drift ;
- cooldown entre demandes ;
- création automatique ou non d'une demande.

Même lorsqu'une politique est déclenchée, DataVision **ne réentraîne pas
silencieusement** le modèle. Il crée une `retraining_request` traçable qui peut
ensuite être traitée par le workflow de modélisation et de revue.

### Assistant

Nouveaux tools gouvernés :

- `get_model_registry_status` ;
- `monitor_model_health` ;
- `check_model_retraining` ;
- `request_model_retraining` ;
- `transition_model_stage`.

Une transition de stage et une demande explicite de réentraînement sont soumises
aux règles de confirmation et aux permissions DataVision.










## Nouveau dans v2.27.0 — Préférences synchronisées & assistant plus réactif

### Affichage intelligent

Le panneau `Aa` se ferme maintenant :
- au clic en dehors du panneau ;
- avec la touche `Esc`.

Raccourcis d'affichage :

```text
Ctrl/Cmd + +   augmenter le zoom UI
Ctrl/Cmd + -   réduire le zoom UI
Ctrl/Cmd + 0   revenir à 100 %
```

Le zoom reste borné entre 90 % et 140 %.

### Préférences utilisateur Enterprise

Lorsqu'un utilisateur est connecté, les préférences suivantes sont synchronisées
avec son profil DataVision :

```text
accessibility_mode
ui_zoom
compact_navigation (réservé pour extension UI)
```

Le navigateur conserve toujours un fallback `localStorage` pour le mode local
et pour garantir une expérience fluide hors connexion Enterprise.

### Assistant plus réactif

Les événements proactifs non critiques sont maintenant coalescés sur une courte
fenêtre et les observations identiques répétées sont dédupliquées.

Objectif : éviter plusieurs appels réseau successifs lorsque l'interface émet
une rafale d'événements équivalents.

Les événements `critical` restent envoyés immédiatement.

Cette optimisation ne modifie ni le Tool Registry, ni les autorisations, ni les
moteurs analytiques.

## Nouveau dans v2.26.1 — Topbar plus pratique

- barre de recherche globale agrandie ;
- libellé plus explicite : `Rechercher dans DataVision…` ;
- raccourci `Ctrl K` conservé ;
- nouveau bouton `⚙` de paramétrage dans la navbar ;
- le bouton de paramétrage ouvre directement l'espace **Gouverner** ;
- responsive conservé sur tablette et mobile.

Aucune logique backend ou analytique n'est modifiée dans ce hotfix.











## Nouveau dans v2.31.0 — Security P0 Closure

### MFA / WebAuthn

DataVision prend désormais en charge les passkeys WebAuthn pour les comptes Enterprise :

```text
mot de passe
   ↓
challenge WebAuthn
   ↓
Windows Hello / Touch ID / clé FIDO2 / passkey
   ↓
session DataVision
```

Après enrôlement d’une passkey, un login par mot de passe exige la seconde étape WebAuthn.
Les challenges sont à usage unique, expirent rapidement et la vérification impose la présence utilisateur.

### Antivirus des uploads

Chaque upload passe par `upload_security.scan_upload()` avant persistance.

Modes :
- `disabled` — développement uniquement ;
- `preferred` — scan si ClamAV est disponible ;
- `required` — fail-closed, recommandé et attendu en production.

Le Docker Compose inclut maintenant un service ClamAV. La signature EICAR de validation est toujours rejetée, même si ClamAV est indisponible.

### Chiffrement des secrets

Les nouveaux secrets utilisent une enveloppe versionnée :

```text
AES-256-GCM
+ key_id
+ nonce aléatoire
+ AAD DataVision
```

Format : `dvkms1:<key_id>:<nonce>:<ciphertext>`.

Les anciens secrets Fernet restent lisibles pour permettre les upgrades sans perte de credentials. En production, `SECRET_KMS_KEY` dédié est exigé par le readiness check. `SECRET_KMS_PREVIOUS_KEYS` permet de conserver les anciennes clés pendant une rotation.

### Readiness production

`/health/ready` vérifie maintenant aussi :
- disponibilité de ClamAV si le mode antivirus est `required` ;
- présence d’une clé KMS dédiée lorsque `APP_ENV=production`.


## Nouveau dans v2.30.0 — CDC Compliance & Production Acceptance

DataVision possède maintenant une matrice de conformité auditable du CDC 1.0.

Le référentiel se trouve dans :

```text
compliance/CDC_COVERAGE_MATRIX.json
docs/CDC_COVERAGE_MATRIX.md
```

Chaque section du CDC contient :
- statut `implemented`, `partial` ou `missing` ;
- priorité P0/P1/P2 ;
- preuves dans le dépôt ;
- tests associés quand ils existent ;
- gap explicite quand la couverture n'est pas totale.

### Score v2.30

```text
Sections CDC       : 75
Implémentées       : 52
Partielles         : 23
Manquantes         : 0
Couverture pondérée: 84,7 %
```

Méthode de calcul :

```text
implemented = 1 point
partial     = 0,5 point
missing     = 0 point
```

Le score n'est pas une certification externe et ne remplace ni les tests
production, ni un audit sécurité, ni l'acceptation utilisateur.

### MVP

Les 16 éléments du MVP obligatoire disposent désormais d'un gate spécifique.
Le gate MVP passe dans v2.30, indépendamment du fait que certaines exigences
V1/V2 plus larges restent partielles.

### Production Acceptance

Deux endpoints sont disponibles :

```text
GET /api/v1/system/cdc-compliance
GET /api/v1/system/production-acceptance
```

Le statut global v2.30 reste `conditional`, notamment à cause de :
- MFA/WebAuthn absent ;
- antivirus d'upload non intégré ;
- validation CI/GitHub réelle à observer sur le dépôt cible ;
- tests de charge/SLO à exécuter sur l'infrastructure cible ;
- validation utilisateur finale encore nécessaire.

Le nouvel écran **Gouverner → CDC & Acceptance** expose le score, les gates,
les gaps prioritaires et les preuves de chaque section.

### Gate CI

Le workflow CI exécute maintenant :

```text
python scripts/cdc_audit.py --check
```

Une preuve référencée dans la matrice qui disparaît provoque donc un échec CI.

## Nouveau dans v2.29.0 — Production Hardening & CI/CD

Cette version ferme le principal écart de validation production du CDC sans
modifier les moteurs analytiques.

### GitHub Actions

Trois workflows sont inclus :

- `CI` : tests backend, typecheck/build frontend, validation Compose et smoke E2E ;
- `Security` : `pip-audit`, `npm audit` et scan filesystem Trivy/SARIF ;
- `Release` : build Docker, build frontend, archive reproductible, SHA256 et SBOM.

### E2E Playwright

Le frontend intègre maintenant Playwright avec des smoke tests vérifiant :

- chargement du shell DataVision ;
- présence de la recherche globale ;
- accès à AI Analyst ;
- disponibilité des contrôles d'affichage.

### Healthchecks

L'API expose désormais :

```text
/health/live
/health/ready
```

`/health/ready` distingue les dépendances obligatoires :

- metadata database ;
- Redis ;

et le sandbox notebook comme dépendance optionnelle signalée séparément.

Le web et le sandbox possèdent également des endpoints/healthchecks dédiés.
Docker Compose attend maintenant des services réellement sains avant de
démarrer leurs dépendants.

### Release reproductible

`scripts/release.py` produit une archive ZIP déterministe :

- ordre de fichiers stable ;
- timestamps ZIP fixes ;
- manifest SHA256 par fichier ;
- SHA256 de l'archive ;
- exclusion de `.env`, `data`, `node_modules`, `.next` et caches.

`scripts/verify_release.py` contrôle l'intégrité du ZIP et son SHA256.

### SBOM

Le repository contient un snapshot CycloneDX des dépendances directes :

```text
sbom/direct-dependencies.cdx.json
```

Le workflow Release génère en plus :

- backend CycloneDX ;
- frontend CycloneDX ;
- source SPDX JSON.

### Sécurité

`SECURITY.md` définit la baseline de promotion production. Les secrets ne sont
jamais inclus dans l'archive reproductible.

### Limite de validation locale

Dans l'environnement de génération de cette version, Docker n'était pas
disponible. La syntaxe Compose est donc fournie et testée par contrat, mais
`docker compose config/build` devra être exécuté par GitHub Actions ou sur la
machine de déploiement avant promotion.

## Nouveau dans v2.28.1 — Zoom réellement global

Correctif du contrôle **Aa / Affichage** : les modes de lecture ne se limitent
plus à la topbar. Ils appliquent maintenant un zoom réel à **toute
l’interface**, notamment :

- contenu principal ;
- AI Analyst ;
- panneaux ;
- tableaux ;
- formulaires ;
- graphiques et cartes de métriques ;
- Model Registry ;
- Decision Lab ;
- Feature Store & Serving ;
- barre latérale et topbar.

Préréglages :

```text
Normal       100 %
Confort      110 %
Grand texte  125 %
```

Les boutons `+` et `−` continuent ensuite à ajuster le zoom entre 90 % et
140 %.

## Nouveau dans v2.28.0 — AI Analyst Performance & Streaming

Cette version améliore directement la réactivité de **AI Analyst**.

### Exécution non bloquante

Le lancement d'une analyse crée maintenant une exécution persistée :

```text
queued
  ↓
running
  ↓
completed / failed / cancelled
```

L'interface n'attend plus une réponse HTTP monolithique pour connaître l'état
de l'analyse.

### Progression SSE

Le frontend reçoit un flux `text/event-stream` contenant :

- progression en pourcentage ;
- étape en cours ;
- outil actuellement exécuté ;
- statut final ;
- résultat final lorsqu'il est disponible.

La barre de progression est donc alimentée par le runtime analytique réel.

### Cache vérifiable

Une requête identique peut réutiliser un résultat déjà calculé si les éléments
suivants sont inchangés :

- dataset et version ;
- révision de la couche sémantique ;
- question ;
- cible/date/groupe/variables ;
- horizon ;
- mode rapide/auto/approfondi ;
- version du moteur AI Analyst.

Le résultat indique explicitement `cache_hit=true`. Aucun faux recalcul n'est
présenté à l'utilisateur.

### Déduplication

Deux demandes identiques lancées simultanément dans le même contexte
utilisateur/workspace partagent la même exécution en cours au lieu de lancer
deux calculs identiques.

### Annulation

Le bouton **Arrêter** demande une annulation coopérative.

L'annulation est vérifiée entre les étapes/outils analytiques. Un calcul
scientifique déjà engagé à l'intérieur d'une librairie ne prétend pas être
préempté instantanément.

### Persistance

Nouvelles tables de métadonnées :

```text
ai_analysis_runs
ai_analysis_cache
```

Le cache est automatiquement invalidé lorsqu'une nouvelle version de dataset,
une nouvelle révision sémantique ou une nouvelle version du runtime est
utilisée.

## Nouveau dans v2.26.0 — Accessibilité d’affichage

Cette version poursuit l’amélioration de l’expérience utilisateur avec un vrai
**pilotage d’affichage** intégré dans la topbar.

### Ajouts

- sélecteur de mode de lecture : `Normal`, `Confort`, `Grand texte` ;
- zoom UI persistant de `90%` à `140%` ;
- mémorisation locale automatique ;
- topbar, boutons, icônes et navigation légèrement agrandis ;
- assistant flottant encore plus lisible ;
- adaptation mobile renforcée pour la topbar et les réglages d’affichage.

### Emplacement

Le contrôle d’affichage se trouve dans la topbar, via le bouton :

```text
Aa 105%
```

### Notes techniques

Le réglage s’applique côté frontend et ne modifie ni les datasets, ni les
analyses, ni les endpoints API.

## Nouveau dans v2.25.1 — Confort visuel & lisibilité

Cette version est un **hotfix UI** centré sur la lisibilité, surtout dans
l'espace **AI Analyst** et dans l'interface générale.

Améliorations principales :
- taille de police globale légèrement augmentée ;
- topbar, navigation latérale et badges plus lisibles ;
- titres, sous-titres et textes descriptifs agrandis ;
- tableaux, panneaux et formulaires plus confortables ;
- zone **Demande analytique**, sélecteurs et exemples AI Analyst agrandis ;
- palette de commande plus lisible ;
- fenêtre de l'assistant flottant légèrement plus grande avec textes agrandis ;
- meilleur rendu responsive quand l'écran est plus étroit.

Aucune logique métier, aucun endpoint API et aucun workflow MLOps n'ont été
modifiés dans cette version.

## Nouveau dans v2.25.0 — Feature Store & Serving

### Feature Store persistant

Le module **Modéliser → Feature Store & Serving** permet de créer des Feature
Sets déclaratifs à partir d'un dataset gouverné.

Chaque Feature Set conserve :
- dataset source ;
- entity keys ;
- event time optionnel ;
- features ;
- types/familles de données ;
- hash SHA256 du schéma ;
- statut draft / active / archived.

Une matérialisation crée un **snapshot immuable** DataVision et enregistre :
- version du dataset source ;
- dataset matérialisé ;
- nombre de lignes ;
- hash du contrat.

Aucun code Python utilisateur n'est stocké ou exécuté par le Feature Store.

### Training / Serving Consistency

Chaque modèle expose désormais un Feature Contract calculé depuis son dataset
d'entraînement :

```text
features requises
+ familles de types
+ schema_sha256
+ policy
```

Le serving refuse :
- les features obligatoires absentes ;
- les valeurs non convertibles vers un type numérique attendu ;
- plus de 5 000 lignes dans une requête interactive.

Les colonnes supplémentaires sont ignorées pour l'inférence mais signalées
dans la réponse.

### Serving interne DataVision

Un modèle champion en production peut être exposé via un endpoint interne :

```text
POST /api/v1/datasets/serving/{endpoint_key}/predict
```

Backends v2.25 :

```text
datavision_internal
datavision_internal_batch
```

La version ne prétend pas déployer automatiquement vers Kubernetes, Vertex AI,
SageMaker ou un gateway cloud externe.

### Champion / Shadow / Canary

Trois stratégies sont disponibles :

- `champion` : tout le trafic utilise le champion ;
- `shadow` : le champion répond à l'utilisateur et le challenger est évalué
  silencieusement pour calculer une comparaison ;
- `canary` : une fraction configurée du trafic est routée vers le challenger.

Le canary utilise un hash déterministe du `request_id`. Une même requête stable
est donc routée vers le même modèle.

### Confidentialité du serving

Les logs de serving ne stockent pas les lignes d'entrée.

Ils enregistrent uniquement :
- request_id ;
- modèle utilisé ;
- stratégie ;
- nombre de lignes ;
- latence ;
- hash SHA256 de la requête ;
- résumé shadow ;
- timestamp.

### Rollback gouverné

Chaque modification d'un deployment crée une révision.

Un rollback :
1. retrouve la révision précédente ;
2. restaure le champion précédent via le Model Registry ;
3. repasse par les gates de production ;
4. retire le champion courant si nécessaire ;
5. restaure le contrat de features ;
6. écrit une nouvelle révision de deployment.

Le rollback ne contourne donc ni certification, ni Responsible AI, ni intégrité
de l'artefact.

### Batch scoring

Le batch scoring :
- accepte un modèle staging ou production ;
- vérifie les features ;
- score le dataset gouverné ;
- crée une **nouvelle version immuable** ;
- ajoute la prédiction et, en classification, les probabilités par classe ;
- conserve le modèle et le Feature Contract dans la provenance de la version.

Le job `batch_scoring` est également supporté par le worker Enterprise.

### Assistant

Nouveaux tools gouvernés :

```text
list_feature_sets
materialize_feature_set
list_model_deployments
score_model_deployment
batch_score_model
rollback_model_deployment
```

Les opérations de matérialisation, batch scoring et rollback exigent une
confirmation humaine.


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


## Correctif v2.31.2 — build Docker

Ce correctif résout un conflit réel du resolver `pip` observé pendant le build Docker :

```text
snowflake-connector-python 4.7.4 requires cryptography>=46.0.5
DataVision v2.31.0 pinned cryptography==46.0.4
```

La dépendance est désormais :

```text
cryptography==46.0.5
```

Le projet Docker utilise aussi explicitement `name: datavision` afin de garder un nom de projet Compose stable, et les scripts Windows utilisent `docker compose down --remove-orphans` avant le redémarrage.

Si des conteneurs d'un build interrompu existent encore, exécuter :

```powershell
.\reset-docker.ps1
docker compose build --no-cache api worker web
docker compose up -d
docker compose ps
```

Le script de reset conserve les volumes de données PostgreSQL, Redis et ClamAV.

## v2.31.2 — Build Windows auto-vérifié

Pour éviter de construire accidentellement une ancienne copie du projet, exécutez :

```powershell
Get-Content .\VERSION
Select-String -Path .\backend\requirements.txt -Pattern '^cryptography'
.\rebuild-windows.ps1
```

Les deux premières commandes doivent afficher respectivement `2.31.2` et `cryptography==46.0.5`.
Le script `rebuild-windows.ps1` arrête immédiatement le processus si le build Docker échoue et ne lance jamais `docker compose up` avec une ancienne image.



## Nouveau dans v2.32.0 — Context Engine v2

Cette version rend le contexte de l’assistant plus durable, plus visible et plus sûr.

- mémoire conversationnelle compacte persistée dans les métadonnées ;
- aucun transcript brut de conversation n’est stocké par ce mécanisme ;
- synchronisation explicite avec le dataset, la version, le modèle, la vue et la variable active ;
- purge automatique des références de colonnes lors d’un changement de dataset ;
- relances elliptiques comprises : `et sa période ?`, `et ses colonnes ?`, `et sa version ?` ;
- `compare avec Profit` peut réutiliser la variable précédemment focalisée ;
- panneau **Contexte actif** visible dans l’assistant flottant ;
- affichage vérifiable du dataset, de la vue, de la version, des dimensions, de la qualité et de la période détectée.

La logique reste fail-safe : si une référence ne peut pas être déterminée de manière fiable, DataVision demande une clarification au lieu d’inventer.

## Nouveau dans v2.31.3 — Assistant réellement conscient du dataset actif

Cette version corrige le cas où l’assistant affichait bien un dataset dans son contexte mais répondait comme s’il ne savait pas l’exploiter.

- nouvelle intention déterministe `dataset_context` ;
- détection de la couverture temporelle du dataset lors du profilage ;
- injection du nom, de la version, du schéma et de la couverture temporelle dans `AssistantContext.uiState` ;
- réponses instantanées, sans LLM, aux questions factuelles sur le dataset actif ;
- ligne de contexte de l’assistant plus lisible (nom du dataset et variable sélectionnée au lieu de l’UUID seul).

Exemples désormais compris directement :

```text
À quelle période remonte ce dataset ?
Combien de lignes contient-il ?
Quelles sont ses colonnes ?
Quel dataset est actif ?
Quelle est sa version ?
```


## Nouveau dans v2.33.0 — Context Engine v3

Le contexte conversationnel ne se limite plus au dataset et à la variable active.
DataVision mémorise maintenant des **artefacts analytiques compacts** issus des
outils déterministes : résultats statistiques, graphiques, modèles, rapports,
explications et scénarios de décision.

Exemples de relances désormais résolues :

- `explique ce résultat` ;
- `compare ce résultat au précédent` ;
- `refais ce graphique avec Profit` ;
- `utilise ce modèle pour prédire` ;
- `explique ce modèle`.

La mémoire stocke uniquement des références, paramètres sûrs, métriques et
résumés compacts — jamais un dump illimité des résultats bruts.


## Nouveau dans v2.34.0 — Context Engine v4 & Actions gouvernées

La v2.34 transforme les références conversationnelles en **actions gouvernées**
sans contourner le Tool Registry, les permissions DataVision ni les confirmations
humaines.

### Actions contextuelles sur un modèle récent

L'assistant peut maintenant résoudre le modèle mémorisé dans des demandes comme :

```text
mets ce modèle en production
quel est le statut de ce modèle ?
surveille ce modèle et vérifie le drift
faut-il réentraîner ce modèle ?
réentraîne ce modèle
audite l'équité de ce modèle sur Gender
évalue le risque de ce modèle
```

La référence est résolue vers le `model_id` réellement mémorisé. Le moteur ne
fabrique jamais un identifiant de modèle.

### Human-in-the-loop renforcé

- le `risk` validé par le Tool Registry est propagé jusqu'à l'interface ;
- `human_confirmation_required=true` est désormais contraignant dans le
  planificateur, l'exécuteur et l'API de contrôle ;
- les actions en attente sont présentées dans une carte explicite ;
- l'utilisateur dispose de **Confirmer** et **Refuser** ;
- un refus est persisté côté orchestrateur et annule proprement le plan ;
- une action déjà présentée comme confirmation gouvernée n'affiche plus une
  seconde boîte de dialogue JavaScript redondante.

### Principe de sécurité

Le Context Engine ne donne jamais directement l'autorisation d'exécuter une
action. Il ne fait que résoudre la référence et l'intention. Le plan résultant
passe toujours par le Tool Registry, les contrats typés, RBAC/RLS et la
politique de confirmation habituelle.




## Nouveau dans v2.36.0 — Context Engine v6 / Project Memory

DataVision dispose maintenant d'une **mémoire projet gouvernée** distincte de la mémoire de session. Elle conserve uniquement des références compactes vers les artefacts déterministes produits par la plateforme (graphiques, modèles, tests, rapports, RCA et scénarios), jamais le transcript brut de la conversation.

Principales capacités :

- rappel d'une analyse ou d'un modèle produit lors d'une session précédente ;
- isolation par workspace en mode Enterprise et scope local explicite en mode desktop/local ;
- recherche déterministe sur titres, résumés, aliases, colonnes et identifiants ;
- rétention configurable (90 jours / 200 éléments par défaut) ;
- épinglage et oubli explicites ;
- rappel automatique désactivable ;
- invalidation prudente au changement de dataset pour éviter les références croisées ;
- gestion de la politique réservée aux rôles disposant de `workspace:manage` en mode Enterprise ;
- aucun dump de lignes brutes dans la mémoire projet.

L'assistant peut maintenant comprendre des demandes comme :

```text
quelles sont mes analyses précédentes ?
retrouve le modèle d'avant sur Profit
reprends l'analyse de la session précédente
montre-moi les résultats mémorisés du projet
```

La mémoire projet est visible dans **Contexte actif → Mémoire projet**.

## Nouveau dans v2.35.0 — Context Engine v5 / Multi-artifact Memory

DataVision peut maintenant raisonner sur **plusieurs artefacts analytiques mémorisés**
au lieu de toujours prendre le dernier résultat par défaut.

### Références stables

Chaque artefact reçoit une référence stable par type :

```text
Graphique #1
Graphique #2
Modèle #1
Modèle #2
Résultat statistique #1
```

Les références sont attribuées dans l'ordre de création et restent associées à
l'artefact pendant toute la session active.

### Résolution déterministe

Exemples maintenant compris :

```text
refais le deuxième graphique avec Sales
compare le modèle model-xgb au modèle model-cat
utilise ce modèle pour prédire
reprends l'analyse de Sales
compare ce résultat au précédent
```

Les identifiants explicites, ordinaux, noms, algorithmes, variables et alias
connus sont utilisés pour résoudre la référence sans calcul LLM.

### Désambiguïsation fail-safe

Si plusieurs artefacts correspondent à une référence générique comme :

```text
utilise le modèle pour prédire
```

et que plusieurs modèles sont présents, DataVision **ne choisit plus
silencieusement le dernier**. Il liste les candidats et demande :

```text
le premier
le deuxième
ou l'identifiant exact
```

Le démonstratif reste volontairement contextuel : `ce modèle` signifie le
modèle le plus récent du contexte courant.

### Interface

Le panneau **Contexte actif** affiche maintenant jusqu'à cinq résultats
mémorisés avec leur référence stable et, lorsqu'il existe, leur identifiant de
modèle, graphique ou rapport.

La mémoire reste bornée, liée au dataset actif et purgée automatiquement lors
d'un changement de dataset.


## Nouveau dans v2.37.0 — Context Engine v7 / Semantic Project Recall

La mémoire projet peut désormais retrouver un artefact antérieur par proximité sémantique locale et explicable.

- recherche déterministe sans service d'embeddings externe ;
- synonymes analytiques/business FR/EN (ventes/revenue/Sales, bénéfice/profit, régions/Geography, etc.) ;
- boosts de type d'artefact, dataset actif, épinglage, paramètres et période ;
- score de pertinence et raisons de correspondance retournés par l'API ;
- champ de recherche directement dans **Contexte actif → Mémoire projet** ;
- aucune extension des permissions : l'isolation workspace reste autoritaire.


## Nouveau dans v2.38.0 — Semantic Memory Actions

DataVision peut maintenant **agir sur les artefacts retrouvés dans la mémoire projet** sans exécuter directement un payload mémorisé. Les recettes passent toujours par le planificateur déterministe, le Tool Registry, les contrats Pydantic, RBAC/RLS et les confirmations humaines existantes.

### Actions disponibles

- **Ouvrir** : navigue vers le module correspondant et recharge le dataset source si nécessaire ;
- **Relancer** : rejoue la recette compacte uniquement si le dataset source est actif ;
- **Actif** : tente de rejouer la recette sur le dataset actif après validation du schéma ;
- **Dupliquer** : clone la recette mémoire sans modifier le dataset ni le modèle.

Les références UI utilisent un identifiant exact `project-memory:<id>`, ce qui évite qu'une recherche sémantique ambiguë sélectionne le mauvais artefact. Les outils rejouables sont limités à une allow-list déterministe : visualisation, tests statistiques, régression, AutoML et génération de rapport. Les lignes brutes et payloads de prédiction ne sont jamais persistés comme recettes.
