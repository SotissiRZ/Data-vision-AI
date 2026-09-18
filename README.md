# DataVision AI — v1.3.0

DataVision AI est un **Data Intelligence Workspace local et installable** réunissant import, profiling, qualité, préparation versionnée, statistiques, SQL, visualisation, Machine Learning, forecasting, détection d'anomalies, XAI, prédiction, AI Analyst et reporting reproductible dans une même interface.

L'interface conserve l'esprit du DataVision R/Shiny historique tout en utilisant une architecture **Next.js + FastAPI + Python**.

## Ports

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

Les ports 3000 et 8000 ne sont pas utilisés.


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
