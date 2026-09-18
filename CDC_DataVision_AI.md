# CAHIER DES CHARGES — DATAVISION AI

**Version : 1.0 — Août 2026**  
**Statut : Document de référence pour conception et développement**  
**Produit : DataVision AI**  
**Positionnement : Plateforme professionnelle intelligente d'analyse de données**

---

## 1. Vision du produit

DataVision AI est une plateforme professionnelle d'analyse de données destinée à l'ensemble des profils qui travaillent avec la donnée : Data Analysts, Data Scientists, statisticiens, chercheurs, enseignants, étudiants avancés, consultants, BI Analysts, ML Engineers et équipes R&D.

Le produit doit transformer un flux de travail traditionnel :

> importer → nettoyer → explorer → analyser → modéliser → interpréter → présenter

en un environnement intégré :

> **connecter → comprendre → préparer → analyser → modéliser → expliquer → collaborer → décider**

DataVision AI ne doit pas être conçu comme un simple dashboard, un notebook ou un chatbot posé au-dessus d'un tableau de données. L'ambition est de construire un **Data Analysis Workspace AI-native**, capable d'assister l'utilisateur tout au long du cycle de vie d'une analyse, tout en conservant la traçabilité, la reproductibilité et le contrôle humain.

Le marché 2026 impose déjà la recherche en langage naturel, la génération d'insights, la détection d'anomalies et les assistants analytiques. La différenciation de DataVision doit donc se situer dans la profondeur du workflow, la fiabilité, la transparence des calculs, l'interopérabilité et l'orchestration d'agents spécialisés plutôt que dans la présence d'un simple chatbot.

---

# 2. Existant à préserver et à dépasser

Le dépôt historique Data_vision_R est une application R/Shiny. Il contient notamment des modules de statistiques descriptives, régression, ANOVA, ACP et clustering, avec visualisations interactives et tableaux de données. Le code utilise notamment Shiny, shinydashboard, ggplot2, plotly, FactoMineR, factoextra, DT, dplyr, rstatix, ggpubr et psych.

Ces capacités constituent le socle analytique historique et ne doivent pas disparaître. Elles doivent être réimplémentées ou exposées dans une architecture moderne.

### Fonctionnalités historiques à conserver

- statistiques descriptives ;
- analyse univariée ;
- analyse bivariée ;
- régression ;
- ANOVA à un facteur ;
- ANOVA à deux facteurs ;
- tests post-hoc ;
- ACP ;
- clustering ;
- visualisations ;
- tableaux interactifs ;
- export de résultats.

### Fonctionnalités à dépasser

L'ancienne interface oblige l'utilisateur à connaître les menus et à choisir manuellement les analyses. La nouvelle plateforme doit proposer un moteur de recommandation analytique et un agent capable de comprendre l'intention de l'utilisateur.

---

# 3. Objectifs

## 3.1 Objectifs principaux

1. Fournir un environnement unique d'analyse de données.
2. Permettre l'import de données provenant de nombreuses sources.
3. Automatiser le profiling et le diagnostic qualité.
4. Assister le nettoyage sans détruire les données originales.
5. Permettre des analyses statistiques professionnelles.
6. Permettre la visualisation interactive.
7. Intégrer le Machine Learning et l'AutoML.
8. Ajouter Explainable AI.
9. Fournir un Data Analyst Agent capable de planifier et exécuter des analyses.
10. Générer automatiquement des rapports reproductibles.
11. Permettre la collaboration.
12. Garantir la traçabilité des opérations.
13. Fournir une API et une architecture extensible.
14. Supporter les utilisateurs techniques et non techniques.
15. Préparer le produit pour une évolution SaaS/Enterprise.

---

# 4. Public cible

## 4.1 Data Analyst

Besoins :

- exploration rapide ;
- SQL ;
- visualisation ;
- KPI ;
- reporting ;
- automatisation ;
- partage.

## 4.2 Data Scientist

Besoins :

- préparation ;
- statistiques ;
- feature engineering ;
- ML ;
- validation ;
- expérimentation ;
- XAI.

## 4.3 Statisticien / Chercheur

Besoins :

- tests ;
- hypothèses ;
- intervalles de confiance ;
- modèles ;
- reproductibilité ;
- rapports méthodologiques.

## 4.4 BI Analyst

Besoins :

- sources multiples ;
- métriques ;
- dashboards ;
- semantic layer ;
- NLQ ;
- reporting.

## 4.5 Étudiant avancé

Besoins :

- apprentissage ;
- analyses guidées ;
- explications ;
- visualisations ;
- rapports.

## 4.6 Entreprise / équipe R&D

Besoins :

- gouvernance ;
- sécurité ;
- collaboration ;
- données privées ;
- audit ;
- rôles ;
- connecteurs ;
- déploiement.

---

# 5. Principes produit

DataVision doit respecter les principes suivants :

### 5.1 AI-assisted, not AI-only

L'utilisateur garde le contrôle.

### 5.2 Calculs déterministes

Les nombres, statistiques et métriques doivent être calculés par des moteurs programmatiques, jamais inventés par un LLM.

### 5.3 Reproductibilité

Toute analyse importante doit pouvoir être rejouée.

### 5.4 Explicabilité

L'utilisateur doit pouvoir voir pourquoi une analyse ou un modèle a été proposé.

### 5.5 Provenance

Chaque résultat doit pouvoir être relié aux données et opérations qui l'ont produit.

### 5.6 Human-in-the-loop

Les transformations destructives et actions sensibles nécessitent validation.

### 5.7 Interopérabilité

DataVision doit pouvoir fonctionner avec Python, R, SQL et des formats standards.

---

# 6. Expérience utilisateur globale

Le workflow principal doit être :

```text
Workspace
   ↓
Connect Data
   ↓
Data Profiling
   ↓
Data Quality
   ↓
Prepare Data
   ↓
Explore
   ↓
Analyze
   ↓
Model
   ↓
Explain
   ↓
Generate Insights
   ↓
Report / Dashboard
   ↓
Share / Collaborate
```

---

# 7. Dashboard principal

Le dashboard doit présenter :

- projets récents ;
- datasets récents ;
- analyses récentes ;
- rapports ;
- modèles ;
- alertes qualité ;
- anomalies détectées ;
- suggestions de l'AI Analyst ;
- activité de l'équipe.

---

# 8. Workspaces

Chaque projet doit être organisé dans un Workspace.

Un Workspace contient :

- datasets ;
- connexions ;
- notebooks ;
- analyses ;
- visualisations ;
- modèles ;
- rapports ;
- prompts ;
- agents ;
- utilisateurs ;
- permissions ;
- historique.

---

# 9. Import et connexion aux données

## 9.1 Fichiers

Support obligatoire :

- CSV ;
- XLSX ;
- JSON ;
- Parquet ;
- TXT ;
- ZIP contenant des données.

## 9.2 Bases

Architecture de connecteurs permettant au minimum :

- PostgreSQL ;
- MySQL ;
- MariaDB ;
- SQLite ;
- SQL Server ;
- Oracle ;
- MongoDB.

## 9.3 Cloud / Data Warehouse

Architecture extensible pour :

- BigQuery ;
- Snowflake ;
- Databricks ;
- Amazon Redshift.

## 9.4 APIs

Possibilité de connecter :

- REST ;
- GraphQL ;
- Webhooks.

---

# 10. Data Profiling automatique

À chaque nouveau dataset, DataVision doit générer automatiquement un profil.

### Profil global

- nombre de lignes ;
- nombre de colonnes ;
- mémoire ;
- types ;
- cardinalité ;
- valeurs manquantes ;
- doublons ;
- valeurs uniques ;
- distributions.

### Profil variable

Pour chaque colonne :

- type détecté ;
- min ;
- max ;
- moyenne ;
- médiane ;
- variance ;
- écart-type ;
- quartiles ;
- fréquence ;
- cardinalité ;
- valeurs manquantes ;
- outliers ;
- distribution.

---

# 11. Data Quality Engine

Le moteur doit détecter :

- valeurs manquantes ;
- doublons ;
- incohérences ;
- valeurs aberrantes ;
- mauvais types ;
- dates invalides ;
- catégories incohérentes ;
- formats incohérents ;
- valeurs impossibles ;
- colonnes constantes ;
- forte cardinalité ;
- fuite potentielle de données.

Chaque problème reçoit :

- sévérité ;
- description ;
- impact ;
- recommandation ;
- action automatique possible.

---

# 12. AI Data Quality Assistant

L'IA peut proposer :

> "17,4 % des valeurs de `age` sont manquantes. Je recommande une imputation par médiane car la distribution est asymétrique."

L'utilisateur peut :

- accepter ;
- modifier ;
- refuser ;
- appliquer à une copie.

Toutes les transformations doivent être enregistrées.

---

# 13. Data Preparation Studio

Interface permettant :

- filtrage ;
- tri ;
- renommage ;
- conversion de types ;
- suppression de colonnes ;
- jointures ;
- concaténation ;
- pivot/unpivot ;
- groupby ;
- agrégation ;
- normalisation ;
- standardisation ;
- encodage ;
- imputation ;
- traitement des outliers ;
- feature engineering.

### Pipeline visuel

Chaque transformation doit devenir un nœud.

Exemple :

```text
Raw Data
   ↓
Remove duplicates
   ↓
Impute missing values
   ↓
Encode categories
   ↓
Scale features
   ↓
Clean Dataset
```

Le pipeline doit être sauvegardable et rejouable.

---

# 14. Versioning des datasets

Le système doit permettre :

- version 1 ;
- version 2 ;
- comparaison ;
- rollback ;
- historique des transformations.

Les données originales ne doivent jamais être détruites.

---

# 15. Exploration automatique

Après import, DataVision doit proposer :

- variables importantes ;
- corrélations ;
- tendances ;
- anomalies ;
- distributions ;
- segments ;
- relations possibles.

Exemple :

> "J'ai détecté une corrélation forte entre X et Y. Souhaitez-vous analyser cette relation ?"

---

# 16. Statistical Analysis Engine

Le moteur doit couvrir au minimum :

### Descriptif

- moyenne ;
- médiane ;
- variance ;
- écart-type ;
- quantiles ;
- asymétrie ;
- kurtosis ;
- fréquences.

### Tests

- t-test ;
- Welch ;
- Mann-Whitney ;
- Wilcoxon ;
- chi-square ;
- Fisher ;
- ANOVA ;
- Kruskal-Wallis ;
- corrélation Pearson ;
- corrélation Spearman ;
- tests de normalité ;
- tests d'homoscédasticité.

### Régression

- linéaire ;
- multiple ;
- logistique ;
- régularisée.

### Multivarié

- ACP ;
- analyse factorielle ;
- clustering ;
- classification.

---

# 17. Statistical Test Advisor

L'utilisateur peut demander :

> "Je veux comparer deux groupes."

DataVision analyse :

- nature des variables ;
- taille des échantillons ;
- hypothèses ;
- normalité ;
- indépendance.

Puis recommande :

> Test de Welch recommandé.

Le système doit expliquer :

- pourquoi ;
- hypothèses ;
- niveau de confiance ;
- limites.

---

# 18. Visualization Studio

Visualisations :

- bar ;
- line ;
- area ;
- scatter ;
- histogram ;
- boxplot ;
- violin ;
- heatmap ;
- correlation matrix ;
- density ;
- bubble ;
- treemap ;
- Sankey ;
- geographic maps ;
- time series ;
- PCA ;
- clustering.

### Smart Visualization

L'utilisateur sélectionne des colonnes et DataVision recommande automatiquement les graphiques adaptés.

---

# 19. Natural Language to Visualization

Exemple :

> "Montre-moi l'évolution du chiffre d'affaires par région depuis 2022."

Le système génère :

- requête ;
- graphique ;
- titre ;
- légende ;
- interprétation.

---

# 20. DataVision AI Analyst

C'est la fonctionnalité centrale.

L'agent doit pouvoir :

1. comprendre une demande ;
2. inspecter le dataset ;
3. choisir les outils ;
4. construire un plan ;
5. exécuter les opérations ;
6. vérifier les résultats ;
7. générer les visualisations ;
8. interpréter ;
9. produire un rapport.

### Exemple

Demande :

> "Analyse ce dataset et identifie les facteurs associés au churn."

Agent :

```text
1. Profilage
2. Qualité
3. Variable cible
4. Analyse univariée
5. Corrélations
6. Tests
7. Modèles
8. Validation
9. SHAP
10. Synthèse
```

---

# 21. Agent Architecture

Ne pas créer un seul agent gigantesque.

Architecture recommandée :

```text
Orchestrator Agent
      │
 ┌────┼──────────────┐
 │    │              │
Data  Statistics     ML
Agent Agent          Agent
 │    │              │
 └────┼──────────────┘
      │
Visualization Agent
      │
Report Agent
      │
Quality / Critic Agent
```

Le **Critic/Evaluation Agent** doit contrôler les résultats avant présentation.

Les architectures multi-agents pour l'analytics sont une direction active en 2026, mais DataVision doit surtout privilégier la vérifiabilité et l'auditabilité plutôt que l'autonomie pour elle-même.

---

# 22. AI Reliability Layer

Aucune réponse numérique ne doit être générée directement par le LLM.

Flux :

```text
User Question
      ↓
LLM Planning
      ↓
Tool Selection
      ↓
Python / SQL / R execution
      ↓
Raw Result
      ↓
Validation
      ↓
LLM Explanation
      ↓
Answer
```

L'interface doit pouvoir afficher :

- source ;
- requête ;
- code exécuté ;
- données utilisées ;
- métriques ;
- date d'exécution.

---

# 23. Semantic Layer

DataVision doit introduire une couche sémantique.

Elle définit :

- métriques ;
- dimensions ;
- relations ;
- synonymes ;
- unités ;
- définitions métier ;
- permissions.

Exemple :

```text
Revenue
= SUM(order.amount)

Profit
= Revenue - Costs

Customer
= unique customer_id
```

L'AI Analyst doit utiliser cette couche au lieu de deviner la logique métier.

---

# 24. NLQ / Text-to-SQL

L'utilisateur peut écrire :

> "Quel est le chiffre d'affaires moyen par région en 2025 ?"

DataVision :

1. comprend l'intention ;
2. identifie les métriques ;
3. génère SQL ;
4. valide SQL ;
5. exécute ;
6. génère tableau/graphique ;
7. explique.

---

# 25. AutoML

Créer un module AutoML complet.

### Tâches

- classification ;
- régression ;
- clustering ;
- forecasting.

### Pipeline

```text
Target
 ↓
Data Validation
 ↓
Split
 ↓
Preprocessing
 ↓
Feature Engineering
 ↓
Model Search
 ↓
Hyperparameter Optimization
 ↓
Cross Validation
 ↓
Evaluation
 ↓
Explainability
```

---

# 26. Model Benchmark

Comparer :

- baseline ;
- Logistic Regression ;
- Random Forest ;
- XGBoost ;
- LightGBM ;
- CatBoost ;
- SVM ;
- modèles adaptés au problème.

Métriques selon tâche :

- Accuracy ;
- Precision ;
- Recall ;
- F1 ;
- ROC-AUC ;
- PR-AUC ;
- MAE ;
- MSE ;
- RMSE ;
- R² ;
- MAPE ;
- silhouette score.

---

# 27. AutoML Guardrails

L'AutoML doit détecter :

- target leakage ;
- class imbalance ;
- petit échantillon ;
- variables identifiantes ;
- données temporelles mal séparées ;
- surapprentissage ;
- métrique inadaptée.

Aucune optimisation ne doit se faire sur le test final.

---

# 28. Explainable AI

Pour chaque modèle :

- feature importance ;
- SHAP global ;
- SHAP local ;
- partial dependence ;
- permutation importance ;
- confusion matrix ;
- calibration ;
- contre-factuels lorsque pertinent.

---

# 29. Model Card

Chaque modèle doit disposer d'une fiche :

```text
Model
Dataset
Version
Features
Target
Algorithm
Metrics
Training date
Validation strategy
Known limitations
Fairness metrics
Explainability
```

---

# 30. Forecasting

Supporter :

- séries temporelles ;
- tendances ;
- saisonnalité ;
- intervalles de prédiction.

Modèles possibles selon le cas :

- baselines ;
- ARIMA ;
- ETS ;
- Prophet ;
- gradient boosting ;
- modèles ML avancés.

Le système doit comparer les méthodes plutôt que d'imposer un modèle unique.

---

# 31. Anomaly Detection

DataVision doit détecter :

- anomalies statistiques ;
- anomalies temporelles ;
- anomalies multivariées.

Méthodes :

- Z-score robuste ;
- IQR ;
- Isolation Forest ;
- Local Outlier Factor ;
- Autoencoder selon le volume.

L'utilisateur peut demander :

> "Pourquoi cette anomalie est-elle importante ?"

---

# 32. Automated Insight Engine

Le système surveille les données et identifie :

- changements importants ;
- tendances ;
- anomalies ;
- corrélations ;
- ruptures ;
- segments ;
- valeurs inattendues.

Puis produit des insights priorisés :

```text
Critical
High
Medium
Low
```

---

# 33. Root Cause Analysis

Exemple :

> Le chiffre d'affaires a baissé de 12 %. Pourquoi ?

L'agent décompose :

```text
Revenue -12%
 ├── Region A  -18%
 ├── Product X -23%
 ├── Segment B -11%
 └── Month July -17%
```

Il doit quantifier la contribution de chaque facteur.

---

# 34. What-if Analysis

Permettre des simulations :

> "Que se passe-t-il si les ventes augmentent de 10 % ?"

> "Que se passe-t-il si le prix augmente de 5 % ?"

> "Quel niveau de conversion est nécessaire pour atteindre 1 M€ ?"

Les simulations doivent clairement distinguer :

- données observées ;
- hypothèses ;
- résultats simulés.

---

# 35. AI Data Storytelling

Générer automatiquement :

- résumé ;
- insights ;
- tendances ;
- anomalies ;
- graphiques ;
- recommandations.

Chaque affirmation doit être liée à des résultats calculés.

---

# 36. Report Builder

Créer un éditeur de rapport par blocs :

- texte ;
- tableau ;
- graphique ;
- KPI ;
- insight ;
- modèle ;
- image ;
- code ;
- méthodologie.

Export :

- PDF ;
- DOCX ;
- HTML ;
- Markdown.

---

# 37. Reproducible Analysis

Chaque analyse doit pouvoir être enregistrée sous forme :

```text
Analysis
 ├── Dataset version
 ├── Parameters
 ├── Code
 ├── Outputs
 ├── Model
 ├── Environment
 └── Timestamp
```

Possibilité de :

> "Re-run analysis"

---

# 38. Notebook intégré

Ajouter un notebook professionnel permettant :

- Python ;
- SQL ;
- R.

Les cellules peuvent être exécutées dans un environnement isolé.

Les résultats peuvent être transformés en :

- graphiques ;
- rapports ;
- dashboards.

---

# 39. SQL Workspace

Éditeur SQL avec :

- autocomplete ;
- schema browser ;
- explain query ;
- résultats tabulaires ;
- visualisation ;
- sauvegarde des requêtes ;
- versioning.

---

# 40. Python Workspace

Support :

- pandas ;
- Polars ;
- NumPy ;
- scikit-learn ;
- matplotlib ;
- Plotly.

Le moteur doit pouvoir utiliser DuckDB pour l'analyse locale de fichiers volumineux.

---

# 41. R Workspace

Préserver l'héritage du projet.

Support :

- R ;
- tidyverse ;
- ggplot2 ;
- statistiques ;
- modèles R.

Le code R historique doit être migrable progressivement.

---

# 42. Collaboration

Fonctionnalités :

- partage de workspace ;
- rôles ;
- commentaires ;
- annotations ;
- mentions ;
- validation ;
- historique ;
- versioning.

Rôles :

- Owner ;
- Admin ;
- Data Scientist ;
- Analyst ;
- Viewer.

---

# 43. Data Catalog

Chaque dataset possède :

- nom ;
- description ;
- propriétaire ;
- source ;
- schéma ;
- tags ;
- sensibilité ;
- fréquence de mise à jour ;
- qualité ;
- lineage.

---

# 44. Data Lineage

Afficher :

```text
Source
 ↓
Transformation
 ↓
Dataset
 ↓
Analysis
 ↓
Model
 ↓
Dashboard
 ↓
Report
```

---

# 45. Governance

Support :

- RBAC ;
- audit logs ;
- dataset permissions ;
- column-level permissions si possible ;
- masquage ;
- anonymisation ;
- classification des données ;
- politiques de rétention.

---

# 46. Sécurité

Obligatoire :

- HTTPS ;
- chiffrement au repos ;
- secrets hors code ;
- OAuth2/OIDC ;
- JWT courts ;
- refresh token sécurisé ;
- MFA ;
- rate limiting ;
- CSRF ;
- protection SSRF ;
- validation des fichiers ;
- sandbox d'exécution ;
- isolation des jobs ;
- antivirus sur uploads selon déploiement.

Le code exécuté par les utilisateurs ou les agents doit être isolé et ne jamais disposer par défaut d'un accès arbitraire au système hôte.

---

# 47. Confidentialité IA

Par défaut :

- les données utilisateur ne doivent pas être envoyées à un LLM externe sans consentement/configuration ;
- possibilité de modèles locaux ;
- possibilité de fournisseur cloud configurable ;
- séparation stricte des tenants ;
- journalisation des appels IA ;
- contrôle de rétention.

---

# 48. Model Gateway

Créer une abstraction :

```text
AI Gateway
 ├── OpenAI-compatible
 ├── Anthropic-compatible
 ├── Gemini
 ├── local Ollama
 └── other providers
```

Le reste de l'application ne doit pas dépendre d'un fournisseur unique.

---

# 49. MCP / Tool Connectivity

Prévoir une architecture compatible avec des outils externes et, lorsque pertinent, MCP.

Exemples :

- base SQL ;
- filesystem contrôlé ;
- data catalog ;
- Git ;
- APIs ;
- stockage objet.

Chaque outil doit avoir des permissions explicites.

---

# 50. Plugin System

DataVision doit pouvoir recevoir des extensions :

```text
Plugin
 ├── metadata
 ├── UI
 ├── backend
 ├── analysis
 └── permissions
```

Exemples futurs :

- survival analysis ;
- geospatial ;
- NLP ;
- computer vision ;
- econometrics ;
- bioinformatics.

---

# 51. API publique

REST API documentée avec OpenAPI.

Endpoints conceptuels :

```text
/auth
/workspaces
/datasets
/datasets/{id}/profile
/datasets/{id}/quality
/pipelines
/analyses
/visualizations
/models
/forecasts
/anomalies
/insights
/reports
/ai/chat
/ai/analyses
/jobs
```

---

# 52. Architecture technique cible

## Frontend

Recommandation :

- Next.js ;
- TypeScript ;
- React ;
- Tailwind CSS ;
- shadcn/ui ou système de design équivalent ;
- Plotly/ECharts/Vega-Lite selon besoin.

## Backend

Recommandation :

- Python ;
- FastAPI ;
- Pydantic ;
- SQLAlchemy.

## Data

- PostgreSQL ;
- DuckDB ;
- Polars ;
- Parquet ;
- S3-compatible object storage.

## Async

- Redis ;
- Celery ou équivalent.

## ML

- scikit-learn ;
- XGBoost ;
- LightGBM ;
- CatBoost ;
- PyTorch selon besoin.

## MLOps

- MLflow ;
- model registry ;
- experiment tracking.

## R

- R ;
- RStudio-compatible execution ;
- éventuellement `rpy2` ou microservice R.

## Deployment

- Docker ;
- Docker Compose ;
- Kubernetes optionnel en Enterprise ;
- GitHub Actions.

---

# 53. Architecture logique

```text
                         DATA VISION AI
                               |
          +--------------------+--------------------+
          |                    |                    |
       Frontend             API Gateway          Auth
          |                    |                    |
          +--------------------+--------------------+
                               |
                  +------------+------------+
                  |                         |
             Core Services              AI Platform
                  |                         |
       +----------+----------+       +------+------+
       |          |          |       |             |
     Data      Analysis     ML    Agent         RAG
    Service    Service    Service  Orchestrator  Service
       |          |          |       |
       +----------+----------+-------+
                  |
             Data Layer
       +----------+-----------+
       |          |           |
   PostgreSQL   DuckDB    Object Storage
       |
     Redis
       |
    Workers
```

---

# 54. Architecture multi-tenant

Prévoir dès le départ :

```text
Organization
   ↓
Workspace
   ↓
Users / Roles
   ↓
Datasets
   ↓
Analyses
```

Toutes les requêtes doivent être tenant-aware.

---

# 55. Observabilité

Mettre en place :

- logs structurés ;
- métriques ;
- traces ;
- health checks ;
- job monitoring ;
- AI latency ;
- AI token/cost tracking ;
- model metrics ;
- error tracking.

---

# 56. AI Observability

Mesurer :

- temps de réponse ;
- coût ;
- tokens ;
- taux d'erreur ;
- tool failures ;
- hallucinations détectées ;
- validation failures ;
- user feedback ;
- qualité des analyses.

---

# 57. Evaluation des agents

Créer un dataset de tests avec des questions analytiques connues.

Exemple :

```text
Question
Expected SQL
Expected result
Expected chart
Expected interpretation
```

Tester :

- exactitude ;
- pertinence ;
- sécurité ;
- reproductibilité ;
- cohérence ;
- coût ;
- latence.

Les agents AutoML doivent également être évalués sur leurs décisions intermédiaires, pas uniquement sur la performance finale du modèle.

---

# 58. Testing

## Backend

- unit tests ;
- integration tests ;
- API tests ;
- database tests.

## Frontend

- component tests ;
- E2E.

## Data

- data quality tests ;
- schema tests ;
- regression tests.

## ML

- training tests ;
- data leakage tests ;
- model regression ;
- fairness tests selon cas.

## AI

- prompt tests ;
- tool-call tests ;
- golden datasets ;
- adversarial tests.

---

# 59. Performance

Objectifs initiaux :

- interface fluide ;
- profiling rapide sur datasets raisonnables ;
- exécution asynchrone pour opérations lourdes ;
- streaming des logs ;
- cache des résultats ;
- pagination ;
- lazy loading.

Les opérations longues ne doivent jamais bloquer l'interface.

---

# 60. UX/UI

Le produit doit avoir une apparence de logiciel professionnel moderne.

Éviter :

- dashboard générique ;
- cartes excessives ;
- gradients décoratifs ;
- boutons partout ;
- menus techniques incompréhensibles ;
- interface ressemblant à un projet étudiant.

Inspirations fonctionnelles :

- IDE ;
- notebook ;
- data workspace ;
- analytics platform.

L'interface doit privilégier :

- espace de travail ;
- panneau de données ;
- panneau d'analyse ;
- canvas ;
- command palette ;
- AI assistant contextuel.

---

# 61. Command Palette

Raccourci global :

`Ctrl/Cmd + K`

Actions :

- ouvrir dataset ;
- créer analyse ;
- rechercher ;
- lancer agent ;
- ouvrir SQL ;
- créer rapport ;
- changer workspace.

---

# 62. AI Interaction Design

L'AI Analyst ne doit pas être une fenêtre de chat isolée.

Il doit être contextuel.

Exemple :

Sur un graphique :

> "Explique cette tendance."

Sur une anomalie :

> "Investiguer."

Sur un modèle :

> "Pourquoi cette prédiction ?"

Sur une table :

> "Nettoyer les valeurs incohérentes."

---

# 63. Commandes analytiques rapides

Exemples :

> Analyze dataset

> Profile data

> Find anomalies

> Explain correlations

> Build model

> Compare models

> Generate report

> Find root cause

> Forecast next 6 months

---

# 64. Internationalisation

Prévoir dès le départ :

- français ;
- anglais.

Architecture prête pour :

- arabe ;
- espagnol.

---

# 65. Accessibilité

Respecter :

- navigation clavier ;
- contraste ;
- labels ;
- lecteurs d'écran ;
- taille de police ;
- états de focus.

---

# 66. Plans du produit

## Free

- datasets limités ;
- analyses standards ;
- visualisations ;
- AI limitée.

## Pro

- AutoML ;
- AI Analyst ;
- rapports ;
- connecteurs ;
- collaboration.

## Team

- workspaces ;
- permissions ;
- partage ;
- catalog ;
- audit.

## Enterprise

- SSO ;
- on-premise ;
- private AI ;
- advanced governance ;
- Kubernetes ;
- SLA.

---

# 67. Roadmap

## Phase 0 — Foundation

- architecture ;
- auth ;
- workspace ;
- database ;
- UI system ;
- Docker ;
- CI/CD.

## Phase 1 — Core Analytics

- import ;
- profiling ;
- quality ;
- preparation ;
- statistiques ;
- visualisation.

## Phase 2 — Data Workspace

- SQL ;
- Python ;
- R ;
- pipelines ;
- versioning ;
- notebooks.

## Phase 3 — AI Analyst

- AI gateway ;
- tool calling ;
- orchestrator ;
- NLQ ;
- insights ;
- reports.

## Phase 4 — ML

- AutoML ;
- experiment tracking ;
- XAI ;
- forecasting ;
- anomaly detection.

## Phase 5 — Collaboration

- teams ;
- permissions ;
- comments ;
- catalog ;
- lineage.

## Phase 6 — Enterprise

- SSO ;
- governance ;
- on-premise ;
- private AI ;
- advanced observability.

---

# 68. MVP obligatoire

Le MVP doit contenir :

1. authentification ;
2. workspace ;
3. upload CSV/XLSX/JSON/Parquet ;
4. profiling ;
5. data quality ;
6. data preparation ;
7. statistiques ;
8. visualisations ;
9. SQL local ;
10. AI Analyst ;
11. NLQ ;
12. génération d'insights ;
13. export PDF/HTML ;
14. historique ;
15. Docker ;
16. tests.

Le MVP ne doit pas essayer d'implémenter simultanément tous les connecteurs Enterprise.

---

# 69. V1

Ajouter :

- AutoML ;
- XAI ;
- forecasting ;
- anomaly detection ;
- notebook Python ;
- notebook R ;
- PostgreSQL ;
- MySQL ;
- collaboration ;
- data catalog ;
- lineage ;
- rapports avancés.

---

# 70. V2

Ajouter :

- multi-agent analytics ;
- proactive analytics ;
- root cause analysis ;
- what-if ;
- semantic layer avancée ;
- connecteurs cloud ;
- plugin marketplace ;
- private AI ;
- enterprise deployment.

---

# 71. Critères d'acceptation principaux

### Data import

Un utilisateur peut importer un CSV et obtenir automatiquement un profil exploitable.

### Data Quality

Les problèmes doivent être détectés et expliqués.

### AI Analyst

Une question en langage naturel doit pouvoir produire une analyse réellement exécutée.

### Exactitude

Les chiffres affichés doivent provenir du moteur de calcul.

### Reproductibilité

Une analyse sauvegardée doit pouvoir être rejouée sur la même version du dataset.

### ML

Un modèle doit être entraîné avec validation correcte et métriques adaptées.

### XAI

Une prédiction doit pouvoir être expliquée.

### Security

Un utilisateur ne doit jamais accéder aux données d'un autre tenant.

### Audit

Les opérations importantes doivent être traçables.

---

# 72. Règles impératives pour le développement

1. Ne pas transformer le projet en simple chatbot.
2. Ne pas conserver l'ancienne architecture R/Shiny comme architecture principale.
3. Ne pas supprimer les capacités statistiques historiques.
4. Ne pas utiliser le LLM pour effectuer des calculs numériques.
5. Ne jamais exécuter du code utilisateur non sandboxé.
6. Ne jamais envoyer des données privées à un fournisseur IA sans configuration explicite.
7. Ne pas créer de fausses fonctionnalités.
8. Ne pas utiliser de données fictives pour masquer une fonctionnalité non implémentée.
9. Toute fonctionnalité doit avoir un état explicite : implemented / partial / planned.
10. Toute opération IA importante doit être vérifiable.
11. Toute transformation de données doit être réversible ou versionnée.
12. Ne pas sacrifier la qualité analytique pour une interface spectaculaire.
13. L'UX doit être professionnelle et orientée workflow.
14. Le système doit être modulaire et testable.
15. Toutes les variables, secrets et URLs doivent être configurables par environnement.

---

# 73. Livrables développeurs

Le développement doit produire :

- code frontend ;
- code backend ;
- services data ;
- services AI ;
- migrations ;
- modèles ;
- tests ;
- Dockerfiles ;
- docker-compose ;
- documentation API ;
- documentation architecture ;
- README ;
- `.env.example` ;
- CI/CD ;
- documentation de déploiement ;
- documentation utilisateur ;
- documentation IA ;
- scripts d'initialisation ;
- seed de développement clairement identifié.

---

# 74. Definition of Done

Une fonctionnalité n'est considérée comme terminée que si :

- elle fonctionne ;
- elle possède des tests ;
- elle gère les erreurs ;
- elle possède une UI cohérente ;
- elle respecte les permissions ;
- elle est documentée ;
- elle est observable ;
- elle ne casse pas les fonctionnalités existantes ;
- elle fonctionne dans Docker ;
- elle ne contient pas de secrets ;
- elle ne repose pas sur une donnée fictive présentée comme réelle.

---

# 75. Vision finale

DataVision AI doit devenir un environnement où un professionnel peut commencer avec :

> "J'ai ce dataset."

et terminer avec :

> "Je comprends mes données, j'ai identifié les problèmes, j'ai effectué les analyses pertinentes, j'ai construit et évalué mes modèles, je comprends leurs prédictions, j'ai identifié les insights importants et je peux présenter un rapport reproductible."

La valeur de DataVision ne doit donc pas être :

> **"Nous avons ajouté de l'IA à un logiciel statistique."**

mais :

> **"DataVision transforme l'analyse de données en un workflow intelligent, vérifiable, reproductible et collaboratif."**

---

# 76. Prompt de référence pour l'équipe de développement

> Vous développez DataVision AI, une plateforme professionnelle d'analyse de données AI-native.
>
> Vous devez traiter ce cahier des charges comme la spécification produit de référence.
>
> Avant toute modification, auditez le dépôt existant et produisez une cartographie de l'architecture actuelle, des fonctionnalités existantes, des dépendances, des dettes techniques et des fonctionnalités à conserver.
>
> Ne réalisez pas une simple refonte visuelle.
>
> L'objectif est une refonte produit et technique complète.
>
> Ne supprimez aucune capacité analytique historique sans équivalent documenté.
>
> Ne créez pas de chatbot décoratif. L'IA doit appeler des outils réels, exécuter des analyses réelles et citer les résultats calculés.
>
> Aucun LLM ne doit être utilisé comme calculatrice statistique.
>
> Les transformations de données doivent être versionnées.
>
> Les analyses doivent être reproductibles.
>
> Le code utilisateur et le code généré par IA doivent être exécutés dans un environnement sandboxé.
>
> Toutes les fonctionnalités doivent être testées.
>
> Toute fonctionnalité non terminée doit être explicitement marquée comme telle.
>
> Ne simulez jamais une fonctionnalité avec des données fictives dans la version finale.
>
> Construisez le système progressivement selon la roadmap du présent CDC.
>
> Après chaque étape, vérifiez :
>
> - tests ;
> - sécurité ;
> - performance ;
> - UX ;
> - logs ;
> - documentation ;
> - compatibilité Docker.
>
> Le résultat attendu est un produit réellement exploitable par des professionnels de la Data, et non une démonstration technique.

---

# 77. Conclusion

DataVision AI doit être positionné comme un **produit de Data Intelligence**, à mi-chemin entre :

- environnement d'analyse ;
- plateforme statistique ;
- notebook ;
- AutoML ;
- BI augmentée ;
- AI Data Analyst ;
- outil de reporting ;
- plateforme collaborative.

La priorité n'est pas de multiplier les fonctionnalités. La priorité est de construire un workflow cohérent dans lequel **les données, les calculs, les modèles, l'IA et les résultats restent reliés et vérifiables**.

