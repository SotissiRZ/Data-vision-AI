# DataVision AI — v2.5.0

DataVision AI est un **Data Intelligence Workspace local, installable et gouverné** qui relie préparation, statistiques, SQL, visualisation, ML, forecasting, XAI, AI Analyst, couche sémantique, dashboards, reporting reproductible et désormais **surveillance proactive des métriques**.

## Ports

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

Les ports 3000 et 8000 ne sont pas utilisés.

## Nouveau dans v2.5.0 — Proactive Intelligence

La zone **Décider** s'ouvre maintenant sur une **Inbox analytique**. DataVision peut surveiller les métriques certifiées du modèle sémantique, détecter des changements significatifs et conserver les alertes avec leur preuve, leur tendance, leur provenance et les investigations recommandées.

### Détection déterministe

Chaque scan combine :

- variation dernière période / période précédente ;
- anomalie robuste du niveau via médiane/MAD ;
- rupture de la variation par rapport à l'historique ;
- niveaux `medium`, `high`, `critical`.

Aucun LLM n'est utilisé pour produire les valeurs, les seuils ou les scores.

### Inbox persistante

Les alertes peuvent être reconnues, résolues ou ignorées. Un fingerprint empêche la duplication d'une alerte identique lors de scans successifs.

### Investigation guidée

Lorsqu'un signal est détecté, DataVision propose des ventilations par dimensions sémantiques certifiées et un contrôle qualité comme étapes suivantes. Ces suggestions sont des pistes analytiques et ne sont pas présentées comme des conclusions causales.

### Worker Redis

Le type de job `proactive_scan` est désormais disponible pour exécuter une surveillance en arrière-plan. Le scheduler calendaire récurrent reste volontairement marqué `partial`.

### Validation v2.5.0

```text
Backend pytest           : 37 passed
Python compile/syntax    : OK
TS/TSX transpilation     : OK
CSS                      : OK
```

Le build Next.js/Docker complet doit être confirmé dans l'environnement Docker cible.

---

## Historique — v2.4.0 Semantic Orchestration

La v2.4 branche réellement le **Semantic Model Studio v2** sur les expériences utilisées au quotidien : langage naturel, AI Analyst et dashboards. L'utilisateur peut maintenant raisonner en vocabulaire métier sans connaître les tables physiques ni les jointures.

### NLQ multi-tables semantic-first

Une question comme :

```text
Quel est le CA par catégorie ?
```

peut résoudre `CA` vers la métrique certifiée `revenue`, `catégorie` vers une dimension d'une table liée, puis exécuter le Semantic Query Engine. Les jointures sûres sont déterminées par le modèle sémantique ; elles ne sont pas inventées par un LLM.

Le résultat expose :

- le mode d'exécution (`semantic` ou `sql`) ;
- la métrique résolue ;
- les dimensions utilisées ;
- les tables traversées ;
- la version du modèle sémantique ;
- la provenance du calcul.

Une représentation SQL logique peut être affichée pour expliquer le plan, mais elle est marquée non exécutable lorsque l'exécution réelle passe par le moteur sémantique.

### AI Analyst semantic-first

Pour une question métier simple, AI Analyst utilise maintenant `semantic_query` avant de tomber sur une exploration générique. Les intentions explicitement statistiques ou ML gardent la priorité : « prévoir le CA » reste un problème de forecasting, alors que « CA par catégorie » est une requête sémantique.

### Semantic Dashboard Builder

Les dashboards acceptent désormais :

- KPI métier certifiés ;
- graphiques métier multi-tables ;
- filtres sur dimensions liées ;
- cross-filtering sémantique ;
- drill-down sur hiérarchies ;
- comparaison temporelle et YoY sur widgets sémantiques.

Un filtre sur une dimension liée est appliqué au niveau du Semantic Query Engine puis projeté sur la table de faits. Les widgets physiques du même dashboard voient donc le même périmètre de lignes.

### Drill-down hiérarchique

Une hiérarchie comme :

```text
Catégorie → Sous-catégorie → Produit
```

peut maintenant être utilisée directement par un graphique de dashboard. Cliquer sur une barre ajoute le filtre de niveau courant et descend au niveau suivant.

### Jointures multi-hop

Le moteur sémantique sait maintenant traverser un schéma en flocon :

```text
Fact Sales → Product → Category
```

pour calculer une métrique de la table de faits par une dimension située plusieurs relations plus loin. Les chemins restent limités aux relations sûres N:1 / 1:1 avec contrôle anti fan-out.

### Agrégation explicite en langage naturel

Une demande explicite comme « moyenne du chiffre d'affaires » peut temporairement remplacer l'agrégation par défaut d'une métrique de base, sans modifier sa définition gouvernée sauvegardée.

### Validation v2.4.0

```text
Backend pytest                 : 35 passed
Python compileall              : OK
TS/TSX transpilation           : OK
NLQ multi-table                : testé
AI Analyst semantic-first      : testé
Dashboard semantic crossfilter : testé
Drill-down hiérarchique        : testé
Jointure multi-hop             : testé
```

Le build Next.js/Docker complet doit être confirmé dans l'environnement Docker cible avant de considérer le frontend de production validé.

---

## Historique — v2.3.0 Semantic Model Studio v2

La v2.3 transforme la couche sémantique initiale en **modèle métier multi-tables exécutable**. L'objectif est de séparer clairement le schéma physique (fichiers, colonnes, clés) de la logique métier réutilisée par l'analytics.

### Modèle multi-tables

Un modèle sémantique peut maintenant contenir :

```text
Fact table (base)
   │
   ├── N:1 → Dimension Produit
   ├── N:1 → Dimension Client
   └── N:1 → Dimension Calendrier
          │
          ├── Année
          ├── Trimestre
          └── Mois
```

Les relations automatiques sont volontairement limitées à `many_to_one` et `one_to_one`. DataVision vérifie l'unicité de la clé côté dimension et **bloque les jointures qui créeraient un fan-out** susceptible de gonfler artificiellement les métriques.

### Métriques de base et calculées

Les métriques physiques restent déterministes :

```text
Revenue = SUM(sales.revenue)
Cost    = SUM(sales.cost)
```

Les métriques calculées utilisent une expression sûre basée sur les IDs de métriques :

```text
margin_pct = (revenue - cost) / revenue * 100
```

La formule est parsée avec l'AST Python et n'utilise jamais `eval()` ou `exec()`.

### Dimensions, certification et hiérarchies

Chaque dimension possède désormais :

- un ID sémantique stable ;
- une table source ;
- un type (`categorical`, `date`, `numeric`) ;
- des synonymes ;
- un état exposé/masqué ;
- une certification métier.

Les hiérarchies permettent de décrire des chemins comme `Année → Trimestre → Mois` ou `Région → Pays → Ville`.

### Semantic Query Engine v2

Le nouvel endpoint `/semantic/query` calcule les métriques à travers les relations du modèle et prend en charge :

- ventilation par dimensions de la table de faits ou des tables liées ;
- filtres sémantiques ;
- métriques calculées ;
- granularité jour/semaine/mois/trimestre/année ;
- comparaison période précédente ;
- comparaison YoY ;
- cumul ;
- YTD ;
- moyenne mobile ;
- somme mobile.

### Semantic Model Health

Le Studio dispose maintenant d'un validateur qui contrôle :

- tables et colonnes référencées ;
- cardinalité des relations ;
- risque de fan-out ;
- formules calculées et dépendances ;
- cycles entre métriques ;
- dimensions temporelles ;
- hiérarchies ;
- connectivité du graphe depuis la table de faits.

Le Trust Center utilise ce contrôle pour enrichir le score de maturité sémantique.

### Interface professionnelle

Le Semantic Studio est maintenant organisé en onglets :

```text
Modèle & relations
Métriques
Dimensions
Hiérarchies
Query Lab
```

Les tables, relations, métriques calculées et tests de requêtes ne sont donc plus mélangés dans un seul écran dense.

### Validation v2.3.0

```text
Backend pytest          : 31 passed
Python compileall       : OK
TS/TSX transpilation    : OK
Semantic multi-table    : testé
Calculated metrics      : testé
YoY / YTD               : testé
Fan-out protection      : testé
Ports                   : 3005 / 8005
```

Documentation détaillée : `docs/SEMANTIC_LAYER_V2.md`.

---


## Nouveau dans v2.2.0 — Tenant-Aware Data Access

La v2.2 ferme la principale faille restante de la fondation Enterprise : lorsqu’une session Enterprise est active, **le même contexte d’accès est maintenant appliqué à toutes les routes dataset et à tous les moteurs analytiques**, pas seulement au Governance Center.

### Boundary de sécurité centralisée

Chaque appel `/api/v1/datasets/*` reçoit automatiquement le contexte :

```text
Utilisateur
   ↓
Workspace actif
   ↓
Rôle RBAC
   ↓
Dataset lié au workspace ?
   ↓
Policies héritées
   ├── Row-Level Security
   └── Column-Level Security
   ↓
DataFrame gouverné
   ↓
Statistiques / SQL / ML / XAI / AI Analyst / Dashboard / Rapport
```

Le mode local sans authentification reste disponible. En revanche, dès qu’un token Enterprise ou un workspace est fourni, DataVision **ne retombe jamais silencieusement en mode local non gouverné**.

### Enforcement global

Les restrictions s’appliquent désormais à :

- preview, profilage, qualité et statistiques descriptives ;
- tests statistiques, corrélations, régression, ANOVA, ACP et clustering ;
- SQL Workspace et NLQ ;
- Visualization Studio et Dashboard Builder ;
- AutoML, forecasting, anomalies et XAI ;
- AI Analyst ;
- Semantic Layer, Trust Center et Decision Lab ;
- Report Studio ;
- jobs asynchrones Redis/worker.

### Héritage de versions sécurisé

Une policy attachée à une version source protège également les versions dérivées. Les nouvelles versions créées dans un workspace sont automatiquement liées à ce workspace. Lorsque les lignes d’une version dérivée ont déjà été matérialisées après RLS, DataVision conserve un snapshot `policy id + updated_at` afin d’éviter de dépendre d’une colonne de filtre ensuite supprimée, tout en réappliquant automatiquement une policy si elle a été modifiée depuis.

### Correction fail-closed importante

En v2.1, la projection de colonnes pouvait être appliquée avant certains filtres de lignes. La v2.2 applique désormais **RLS avant Column-Level Security**. Une policy qui référence une colonne inexistante ou un opérateur invalide échoue fermée au lieu d’élargir l’accès.

### Frontend tenant-aware

Toutes les fonctions API du frontend injectent automatiquement :

```text
Authorization: Bearer <token>
X-Workspace-ID: <workspace actif>
```

La topbar affiche `Accès gouverné · <rôle>` lorsqu’un dataset est consommé via le boundary Enterprise.

### Validation v2.2.0

```text
Backend pytest : 28 passed
Python compile : OK
RLS global     : testé
CLS global     : testé
SQL gouverné   : testé
Workspace isolation : testé
Version inheritance : testé
Background jobs     : testé
Ports               : 3005 / 8005
```

Documentation détaillée : `docs/TENANT_AWARE_SECURITY.md`.

---

## Nouveau dans v2.1.0 — Enterprise Foundation

La v2.1 transforme la fondation locale en une première plateforme gouvernée multi-utilisateur, sans désactiver le mode local existant. Elle introduit **identité locale, organisations, workspaces, RBAC, metadata store PostgreSQL, audit log, politiques d'accès et jobs Redis**.

### Nouvelle zone `Gouverner`

L'interface v2 dispose maintenant d'un septième espace fonctionnel :

```text
Vue d’ensemble
Données
Analyser
Modéliser
Décider
Publier
Gouverner  ← identité, rôles, policies, jobs, audit
```

Le Governance Center permet d'initialiser un propriétaire, créer des workspaces, provisionner des membres, attribuer les rôles `owner/admin/data_scientist/analyst/viewer`, lier les datasets, définir des politiques de colonnes/lignes, suivre les jobs asynchrones et inspecter le journal d'audit.

### Architecture Enterprise

```text
Browser :3005
      │
      ▼
FastAPI :8005
      │
      ├── PostgreSQL  ← utilisateurs / workspaces / RBAC / audit / jobs
      ├── Redis       ← file de jobs
      ├── Worker      ← AutoML / AI Analyst / forecast / rapports
      └── Data layer  ← Parquet / modèles / rapports / datasets versionnés
```

PostgreSQL est le metadata store principal en Docker. Un fallback SQLite local est disponible pour le développement hors stack.

### Sécurité et limites explicites

La v2.1 applique le RBAC sur les nouvelles ressources Enterprise et exécute réellement un `governed-preview` avec filtres de lignes/colonnes. **L'enforcement des policies sur toutes les anciennes routes analytiques est encore partiel** et reste déclaré comme tel jusqu'à la migration tenant-aware globale. OIDC/SSO, refresh tokens, vault de secrets et annulation préemptive des jobs en cours restent planifiés.

### Validation v2.1.0

```text
Backend pytest : 25 passed
Python compile : OK
TS/TSX parse   : OK
Ports          : 3005 / 8005
Worker Redis   : ajouté au docker-compose
```

Documentation détaillée : `docs/ENTERPRISE_FOUNDATION.md`.

---

## Nouveau dans v2.0.0 — Semantic Intelligence, Trust & Decision Lab

La v2.0 est une refonte produit guidée par un benchmark 2026 de Power BI/Fabric, Tableau, Looker, ThoughtSpot, Dataiku, Alteryx, Metabase et Apache Superset. Le but n'est pas de copier leurs interfaces, mais de retenir les invariants du marché — couche sémantique, analytics conversationnelle, dashboards interactifs, gouvernance, automatisation, ML/XAI — tout en corrigeant deux problèmes fréquents : **complexité d'interface** et **résultats IA difficiles à vérifier**.

### Interface professionnelle orientée workflow

La navigation plate est remplacée par six espaces :

```text
Vue d'ensemble
Données
Analyser
Modéliser
Décider
Publier
```

Chaque espace possède sa sous-navigation contextuelle. Une **Command Palette** globale (`Ctrl/Cmd + K`) ouvre rapidement un module ou transmet une question à AI Analyst. La page d'accueil propose des playbooks orientés objectifs plutôt que des noms de techniques statistiques.

### Semantic Studio

Une couche sémantique locale et versionnée permet de définir :

- métriques métier ;
- agrégation officielle ;
- unités ;
- dimensions ;
- descriptions ;
- synonymes ;
- statut de certification ;
- glossaire métier.

Le NLQ et AI Analyst utilisent cette couche pour résoudre les termes métier vers les colonnes physiques. Les synonymes et métriques certifiées apparaissent dans la provenance analytique.

### Metric Pulse

Une métrique sémantique peut être suivie dans le temps avec valeur courante, tendance, variation de période et signal simple d'anomalie. Les calculs restent déterministes.

### Trust Center

Le Trust Center agrège quatre axes : qualité des données, maturité sémantique, reproductibilité/lineage et signaux de confidentialité. Il affiche également les politiques d'exécution : résultats numériques par moteurs déterministes et données brutes non envoyées par défaut à un LLM externe.

### Decision Lab

Le Decision Lab exécute de vrais scénarios sur le pipeline de modèle sauvegardé :

- référence + scénarios d'override ;
- variation de prédiction ;
- variation de probabilité en classification ;
- courbe de sensibilité d'une variable.

Le produit indique explicitement qu'un what-if prédictif décrit la réponse du modèle et **n'établit pas un effet causal**.

### NLQ et AI Analyst sémantiquement ancrés

Le text-to-SQL et l'orchestrateur reconnaissent les labels et synonymes métier. Une demande explicite d'agrégation (« moyenne », « somme », etc.) prend priorité sur l'agrégation par défaut de la métrique, tandis que la métrique et la dimension gouvernées fournissent le contexte.

### Validation v2.0.0

```text
Backend          : 23 tests passent
Python compileall: OK
TSX / TypeScript : transpilation syntaxique OK
CSS              : accolades équilibrées
Ports            : 3005 / 8005
```

Le build Next.js/Docker complet reste à confirmer sur la machine cible, comme pour les versions précédentes.

Voir :

- `docs/MARKET_BENCHMARK_2026.md`
- `docs/PRODUCT_STRATEGY_2026.md`
- `docs/UI_ARCHITECTURE_V2.md`


## Nouveau dans v1.3.0 — Dashboard Builder interactif

La v1.3 ajoute un vrai **Dashboard Builder** au-dessus des moteurs analytiques existants. L'objectif est de permettre une exploration décisionnelle persistante sans transformer l'application en simple collection de graphiques.

### Composition

- nouveau module **Dashboards** dans la navigation ;
- widgets KPI, barres, courbe, histogramme, scatter, heatmap et texte ;
- tailles Petite / Moyenne / Large / Pleine largeur ;
- réorganisation des cartes par glisser-déposer natif ;
- panneau de propriétés pour modifier titre, métrique, variables, agrégation et contenu ;
- dashboards enregistrés localement et verrouillés sur la lignée du dataset.

### Filtres globaux et cross-filtering

Les filtres supportent égalité, différence, texte contient, comparaisons, intervalle, valeurs nulles et non nulles. Ils sont appliqués côté backend avant tout calcul de KPI ou de graphique.

Les graphiques en barres sont interactifs : cliquer sur une catégorie crée un **cross-filter** global et recalcule tous les widgets sur le sous-ensemble correspondant. L'interface affiche en permanence le nombre de lignes visibles par rapport au dataset initial.

### Calculs reproductibles

Chaque aperçu de dashboard passe par `POST /api/v1/datasets/{id}/dashboards/preview`. Le backend applique les filtres puis appelle les mêmes moteurs déterministes que Visualization Studio. Aucun chiffre du dashboard n'est calculé dans le navigateur.

Endpoints :

```text
GET    /api/v1/datasets/{id}/dashboards
POST   /api/v1/datasets/{id}/dashboards
GET    /api/v1/datasets/{id}/dashboards/{dashboard_id}
DELETE /api/v1/datasets/{id}/dashboards/{dashboard_id}
POST   /api/v1/datasets/{id}/dashboards/preview
```

### Validation v1.3.0

```text
Backend : 20 tests passent
Python  : compileall OK
TSX/TS  : transpilation syntaxique OK
Ports   : 3005 / 8005
```

Le build Next.js/Docker complet reste à confirmer sur la machine cible.

Voir `docs/DASHBOARD_BUILDER.md`.

## Nouveau dans v1.2.0 — Report Intelligence

La v1.2 transforme le Report Studio en **moteur éditorial analytique**. Le rapport ne se contente plus d’assembler des résultats : il organise automatiquement les éléments les plus utiles, construit une lecture hiérarchisée et documente les limites d’interprétation.

### Narration analytique automatique

- génération d’une section **Résultats clés et lecture analytique** ;
- constats classés par priorité avec **preuve calculée** et **interprétation** ;
- synthèse de qualité, complétude, corrélations, asymétries, concentrations catégorielles et tendances temporelles lorsque les données le permettent ;
- intégration optionnelle des constats d’une session AI Analyst ;
- conclusion de lecture construite à partir des résultats réellement calculés.

### Sélection intelligente des figures

DataVision peut générer automatiquement, sans exiger qu’elles aient été préalablement épinglées :

- manquants par variable ;
- heatmap de corrélation ;
- scatterplot de la relation numérique la plus forte ;
- histogramme d’une variable informative ;
- comparaison catégorie/mesure ;
- série temporelle lorsqu’une date exploitable est détectée.

Chaque figure automatique conserve son **objectif**, sa **lecture**, la version du dataset et sa provenance. Le nombre maximal de figures est configurable dans Report Studio.

### Limites et précautions

Une section dédiée explicite automatiquement les principaux risques d’interprétation : valeurs manquantes, qualité, petit échantillon, variables identifiantes, limites temporelles et absence de preuve causale. Les corrélations sont présentées comme associations et non comme causalité.

### Meilleure détection des identifiants

Une variable numérique continue n’est plus exclue uniquement parce que ses valeurs sont presque toutes uniques. L’exclusion automatique vise désormais les colonnes réellement susceptibles d’être des identifiants (`id`, `*_id`, UUID, clés, numéros d’enregistrement, etc.). Cela évite de masquer des mesures continues utiles dans les graphiques et analyses automatiques.

### Validation v1.2.0

```text
Backend : 19 tests passent
Python  : compileall OK
PDF     : QA visuelle OK (13 pages rendues et inspectées)
DOCX    : QA visuelle OK (13 pages rendues et inspectées)
TSX/TS  : transpilation syntaxique OK
```

Le build Next.js/Docker complet reste à confirmer sur la machine cible.

Voir `docs/REPORT_INTELLIGENCE.md`.

## Nouveau dans v1.1.1 — Professional Report Studio

Le module **Rapports** a été entièrement repensé. Il ne produit plus une simple succession de blocs : il compose désormais un document professionnel structuré et visuel.

### Report Studio

- trois modèles : **Exécutif**, **Analytique** et **Technique** ;
- page de garde avec titre, sous-titre, dataset, version, auteur/organisation et date ;
- sommaire automatique et sections numérotées ;
- **synthèse exécutive** avec KPI, constats prioritaires et recommandations ;
- sélection explicite des sections du document ;
- sélection individuelle des visualisations épinglées à publier ;
- aperçu de type document directement dans l'interface avant export ;
- historique des rapports avec indication du modèle utilisé.

### Exports professionnels

- PDF avec page de garde, en-têtes/pieds de page, pagination, KPI, tableaux stylés et graphiques vectoriels ;
- DOCX avec styles, sommaire statique, tableaux professionnels, pagination et **graphiques intégrés sous forme d'images** ;
- HTML imprimable avec mise en page responsive, page de garde, sommaire cliquable, KPI et graphiques SVG ;
- Markdown réorganisé avec sommaire, numérotation et synthèse exécutive.

Les graphiques épinglés ne sont plus remplacés par de simples extraits de données : DataVision rend réellement les graphiques `bar`, `line`, `area`, `histogram`, `density`, `scatter`, `heatmap` et `box` dans les exports compatibles.

### Validation v1.1.1

```text
Backend : 18 tests passent
Python  : compileall OK
PDF     : rendu visuel QA OK (9 pages testées)
DOCX    : rendu visuel QA OK (9 pages testées)
TSX/TS  : transpilation syntaxique OK
```

Voir `docs/REPORT_STUDIO.md`.

## Nouveau dans v1.1.0 — dashboard analytique & visualisations épinglées

- l’accueil devient un **Analytical Overview** dès qu’un dataset est actif ;
- KPI de structure et de qualité visibles immédiatement ;
- graphiques automatiques pour valeurs manquantes, types et corrélations fortes ;
- feed **Insights clés** calculé à partir des résultats déterministes ;
- recommandations de visualisations et raccourcis vers les modules pertinents ;
- identifiants probables exclus des corrélations automatiques du dashboard ;
- bouton **Ajouter au rapport** dans Visualization Studio ;
- registre local des visualisations épinglées, verrouillées sur la version du dataset ;
- nouvelle section **Visualisations épinglées** dans le Report Builder ;
- endpoint `GET /api/v1/datasets/{id}/dashboard` ;
- endpoints `GET/POST /api/v1/datasets/{id}/visualizations/saved`.

Voir `docs/ANALYTICAL_DASHBOARD.md`.

### Validation v1.1.0

```text
Backend : 17 tests passent
Python  : compileall OK
TSX/TS  : transpilation OK + strictNullChecks ciblé OK
```

Le build Next.js/Docker complet reste à confirmer sur la machine cible.

## Nouveau dans v1.0.2 — interface analytique plus lisible & diagnostics visuels

Cette version poursuit l’épuration de l’interface et ajoute des visualisations statistiques qui manquaient pour interpréter les résultats sans dépendre uniquement des tableaux numériques.

### Navigation et ergonomie

- navigation regroupée en quatre blocs : **Explorer**, **Analyser**, **Modéliser** et **Partager** ;
- menu latéral plus compact et hiérarchie plus claire ;
- panneaux de configuration statistiques simplifiés ;
- tableaux techniques placés dans des sections repliables lorsque le graphique est plus utile en première lecture ;
- identifiants probables (`ID`, `*_id`, colonnes quasi uniques) détectés et exclus des sélections analytiques automatiques ;
- identifiants toujours accessibles manuellement lorsqu’ils sont réellement nécessaires.

### Tests statistiques : au-delà de la p-value

Les résultats des tests incluent désormais, lorsque la méthode le permet :

- **Cohen d** pour Student/Welch ;
- **corrélation bisérielle de rang** pour Mann–Whitney ;
- **eta²** pour ANOVA à un facteur ;
- **epsilon²** pour Kruskal–Wallis ;
- **r / rho** pour Pearson et Spearman ;
- **V de Cramér** pour le chi-deux ;
- **odds ratio** pour Fisher ;
- **Cohen dz** pour le t apparié.

Les écrans affichent aussi, selon le test :

- boxplots et synthèses par groupe ;
- nuage de points pour les corrélations ;
- heatmap d’intensité pour les tableaux de contingence ;
- diagnostics statistiques repliables.

### Régression : diagnostics professionnels

La page Régression contient maintenant :

- forest plot des coefficients avec **IC 95 %** et ligne de référence à zéro ;
- résidus vs valeurs ajustées ;
- **Q-Q plot** des résidus ;
- histogramme des résidus ;
- observé vs prédit ;
- Shapiro-Wilk et Breusch-Pagan ;
- observations les plus influentes selon la **distance de Cook** ;
- AIC/BIC et informations techniques repliables.

### ANOVA

- **eta²** pour l’ANOVA à un facteur ;
- **eta² partiel** pour l’ANOVA à deux facteurs ;
- visualisation des intervalles de confiance à 95 % du post-hoc Tukey ;
- boxplots par groupe conservés pour la lecture des distributions.

### Forecasting et XAI

- benchmark Forecasting complété par des graphiques **RMSE** et **MAE** ;
- XAI régression enrichi avec résidus vs prédictions et observé vs prédit ;
- résultats numériques détaillés conservés mais moins envahissants dans l’interface.

### Validation v1.0.2

```text
Backend : 16 tests passent
Python  : compileall OK
TS/TSX  : syntaxe validée par transpilation TypeScript
```

Le build Docker/Next complet reste à confirmer sur la machine cible, car c’est elle qui possède l’environnement npm/Docker complet.

## Fonctionnalités v1.0

### Report Builder reproductible

L'onglet **Rapports** est maintenant fonctionnel. Un rapport peut inclure :

- vue d'ensemble du dataset ;
- qualité des données ;
- statistiques descriptives ;
- une session AI Analyst précise ;
- méthodologie ;
- provenance complète.

Chaque rapport est verrouillé sur **l'identifiant et la version exacte du dataset** utilisés lors de sa génération.

Exports réels :

```text
PDF
DOCX
HTML
Markdown
```

### Historique AI Analyst

Chaque analyse AI Analyst est maintenant persistée localement. L'interface permet de rouvrir les sessions précédentes avec :

- question ;
- intention détectée ;
- résultat synthétique ;
- outils exécutés ;
- Critic status ;
- provenance ;
- timestamp ;
- version du dataset.

### NLQ / Text-to-SQL contrôlé

Le SQL Workspace accepte désormais des questions en langage naturel, par exemple :

```text
Quelle est la moyenne de sales par region ?
Combien de lignes par segment ?
Quelle est la somme de revenue par product ?
Top 10 produits par sales
```

DataVision :

1. identifie les colonnes citées ;
2. construit une requête SQL ;
3. expose les hypothèses et le niveau de confiance ;
4. valide la requête avec le garde-fou SQL read-only ;
5. exécute la requête via DuckDB ou le fallback local.

Le NLQ v1.0 est volontairement déterministe. Les questions ambiguës sont signalées au lieu d'inventer une logique métier.

### Installation Windows simplifiée

Trois scripts PowerShell sont inclus :

```text
install-windows.ps1
start-datavision.ps1
stop-datavision.ps1
```

`install-windows.ps1` vérifie Docker, crée `.env`, construit les images, démarre DataVision et ouvre automatiquement `http://localhost:3005`.

### Builds Docker plus rapides

Les Dockerfiles utilisent maintenant les caches BuildKit :

- cache pip pour le backend ;
- cache npm pour le frontend.

Les reconstructions après une modification de code doivent donc éviter de retélécharger inutilement toutes les dépendances.

## Fonctionnalités disponibles

- import CSV / XLSX / JSON / Parquet / TXT ;
- profiling automatique ;
- Data Quality ;
- préparation et transformations ;
- versioning immuable et rollback ;
- lineage et pipelines sauvegardables/rejouables ;
- feature engineering sécurisé ;
- GroupBy, pivot, unpivot, jointures et concaténations ;
- statistiques descriptives ;
- Statistical Test Advisor ;
- tests paramétriques/non paramétriques ;
- corrélations ;
- régression ;
- ANOVA ;
- ACP ;
- clustering K-means ;
- Visualization Studio ;
- SQL Workspace read-only ;
- NLQ/Text-to-SQL v1.0 ;
- DuckDB / Polars ;
- AutoML ;
- cross-validation et tuning ;
- train/validation/test ;
- guardrails ML ;
- Model Cards ;
- registre local de modèles ;
- prédictions ;
- forecasting ;
- anomalies ;
- XAI global/local ;
- AI Analyst avec orchestration, Critic et provenance ;
- historique AI Analyst ;
- rapports reproductibles PDF/DOCX/HTML/Markdown.

## Installation Windows recommandée

Dans PowerShell, à la racine du projet :

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-windows.ps1
```

Ou manuellement :

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Puis ouvrir :

```text
http://localhost:3005
```

## Démarrage / arrêt ultérieur

```powershell
.\start-datavision.ps1
```

```powershell
.\stop-datavision.ps1
```

## API v1.0 ajoutée

```text
POST /api/v1/datasets/{id}/workspace/nlq

GET  /api/v1/datasets/{id}/ai/history
GET  /api/v1/datasets/{id}/ai/history/{session_id}

GET  /api/v1/datasets/{id}/reports
POST /api/v1/datasets/{id}/reports
GET  /api/v1/datasets/{id}/reports/{report_id}
GET  /api/v1/datasets/{id}/reports/{report_id}/export/{format}
```

Formats d'export : `pdf`, `docx`, `html`, `md`.

## Validation

Backend :

```text
16 passed
```

Les tests couvrent notamment :

- tout le socle v0.1 → v0.9 ;
- persistance de l'historique AI Analyst ;
- NLQ → SQL → exécution ;
- génération de rapport verrouillée sur le dataset ;
- exports PDF, DOCX, HTML et Markdown.

Compilation Python : `OK`.

La syntaxe de `page.tsx` et `lib/api.ts` a été validée par transpilation TypeScript après les ajustements v1.0.2. Le build Docker/Next complet reste à valider dans votre environnement Docker, qui constitue désormais l’environnement de référence.

## Documentation incluse

```text
docs/
├── AI_ANALYST.md
├── ARCHITECTURE.md
├── CHANGELOG.md
├── FORECASTING_ANOMALY_XAI.md
├── ML_AUTOML.md
├── UI_VISUAL_ANALYTICS.md
├── REPORTING_NLQ.md
├── README_DEVELOPPEMENT.md
├── ROADMAP_EXECUTION.md
└── VALIDATION.md
```

## Limites explicites de v1.0

- le NLQ est déterministe et ne couvre pas encore toute la grammaire SQL ;
- aucune couche sémantique métier avancée n'est encore utilisée pour désambiguïser les métriques ;
- SHAP complet reste partiel ;
- authentification, vrais workspaces multi-utilisateurs, RBAC, collaboration et SSO restent à implémenter ;
- l'installation actuelle est Docker/PowerShell, pas encore un exécutable Windows natif `.exe` ;
- l'exécution asynchrone Celery/Redis des jobs lourds reste à renforcer.

## Principe de fiabilité

Les calculs statistiques, SQL, ML, forecasting et métriques restent exécutés par des moteurs programmatiques. La couche IA sert à comprendre, planifier, orchestrer, contrôler et expliquer — jamais à inventer les résultats numériques.
