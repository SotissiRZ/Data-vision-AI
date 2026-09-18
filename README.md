# DataVision AI — v1.0.2

DataVision AI est un **Data Intelligence Workspace local et installable** réunissant import, profiling, qualité, préparation versionnée, statistiques, SQL, visualisation, Machine Learning, forecasting, détection d'anomalies, XAI, prédiction, AI Analyst et reporting reproductible dans une même interface.

L'interface conserve l'esprit du DataVision R/Shiny historique tout en utilisant une architecture **Next.js + FastAPI + Python**.

## Ports

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

Les ports 3000 et 8000 ne sont pas utilisés.

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
