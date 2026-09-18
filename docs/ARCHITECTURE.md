# Architecture — DataVision AI v0.9

```text
Next.js UI :3005
   |
FastAPI /api/v1 :8005
   |
   +-- Dataset / Profiling / Quality
   +-- Preparation / Versioning / Pipelines
   +-- Statistical Engine
   +-- Visualization Engine
   +-- Data Workspace
   |      +-- DuckDB preferred
   |      +-- Polars
   |      +-- SQL read-only
   +-- Advanced Analysis
   |      +-- Regression
   |      +-- ANOVA
   |      +-- PCA
   |      +-- Clustering
   +-- ML Platform
   |      +-- Guardrails
   |      +-- Train / Validation / Test
   |      +-- Cross-validation
   |      +-- AutoML
   |      +-- Model Registry / Cards
   |      +-- Prediction / XAI
   +-- Forecasting / Anomaly Detection
   |
   +-- AI Analyst
          +-- Intent Router
          +-- Tool Registry
          +-- Orchestrator
          +-- Critic
          +-- Findings
          +-- Provenance

Immutable dataset versions
Local model artifacts (.joblib + .card.json)
```

## AI Reliability Layer

```text
Natural-language request
      ↓
Intent / variable resolution
      ↓
Analytic plan
      ↓
Executable tool
      ↓
Raw calculated result
      ↓
Critic checks
      ↓
Evidence-backed finding
      ↓
User-facing explanation
```

Aucun nombre n'est produit par un modèle de langage. Le noyau v0.9 fonctionne sans LLM externe.

## Politique de validation ML

```text
Dataset
  |
  +-- 60% Train
  |     +-- K-fold cross-validation
  |     +-- hyperparameter search
  |
  +-- 20% Validation
  |     +-- model comparison / selection
  |
  +-- 20% Final Test
        +-- used only after selection
        +-- final metrics
        +-- permutation importance
```

Le jeu de test final ne participe ni au benchmark, ni au tuning.

## Forecasting / Anomaly / XAI

- `services/forecasting.py` : séries temporelles, validation chronologique, benchmark, prévisions ;
- `services/anomaly_detection.py` : IQR, MAD/z robuste, Isolation Forest ;
- `services/xai.py` : diagnostics globaux et explications locales ;
- les artefacts ML persistent les baselines de variables et les indices du test final.

## AI Analyst

- `services/ai_analyst.py` contient le routeur, le registre d'outils, l'orchestrateur, la synthèse déterministe et le Critic ;
- les routes sont exposées sous `/api/v1/datasets/{id}/ai/*` ;
- les artefacts retournés sont tronqués pour l'affichage mais les moteurs sont réellement exécutés ;
- les erreurs ne sont pas transformées en faux résultats.

## v1.0 — persistance analytique et reporting

```text
AI Analyst
   └── data/analyses/<session_id>.json

Report Builder
   ├── verrou dataset/version
   ├── session AI optionnelle
   ├── data/reports/<report_id>.json
   └── exports PDF / DOCX / HTML / Markdown

SQL Workspace
   └── NLQ déterministe → SQL read-only validé → DuckDB/SQLite fallback
```

Les rapports et historiques sont actuellement stockés localement sur le volume `./data`. La migration vers PostgreSQL/object storage est prévue avec la couche workspace/multi-utilisateur.

## v2.0 — Semantic Intelligence, Trust & Decision

```text
Business question
      │
      ├── Semantic Layer
      │     ├── metrics
      │     ├── dimensions
      │     ├── synonyms
      │     ├── units
      │     └── certification
      │
      ├── AI Analyst / NLQ
      │     └── semantic grounding
      │
      ├── Deterministic engines
      │     ├── SQL / DuckDB
      │     ├── statistics
      │     ├── ML / forecasting
      │     └── XAI
      │
      ├── Critic + Trust Center
      │     ├── quality
      │     ├── provenance
      │     ├── reproducibility
      │     └── privacy signals
      │
      └── Decision Lab
            ├── saved-model inference
            ├── what-if scenarios
            └── sensitivity
```

La couche sémantique reste locale et dataset-root-aware. Les métriques calculées sont exécutées par code, jamais par un LLM. Le Decision Lab réutilise le pipeline de modèle sauvegardé et marque explicitement les scénarios comme non causaux.

### Professional shell

La structure d'information passe à six espaces : Vue d'ensemble, Données, Analyser, Modéliser, Décider, Publier. La sidebar affiche les espaces ; les modules sont exposés dans une sous-navigation contextuelle. `Ctrl/Cmd + K` permet navigation et handoff vers AI Analyst.

## v2.3 — Semantic Model Runtime

Le runtime sémantique est situé dans `backend/app/services/semantic_layer.py`.

```text
Dataset base
  + tables liées visibles dans le workspace
        ↓
Semantic Model JSON (versionné par root dataset)
        ↓
Validator
  - colonnes
  - cardinalité
  - fan-out
  - formules
  - cycles
  - hiérarchies
        ↓
Semantic Query Engine
  - relations sûres
  - filtres
  - agrégations
  - métriques calculées
  - time intelligence
        ↓
API /semantic/query
```

Toutes les tables liées passent par `storage.load_dataframe()`. En contexte Enterprise, elles reçoivent donc le même boundary tenant-aware (RBAC/RLS/CLS) que les autres moteurs.

## v2.4 — Semantic Orchestration Runtime

La couche sémantique devient un service transversal utilisé par trois surfaces principales :

```text
                  Semantic Model v2
                         │
          ┌──────────────┼──────────────┐
          │              │              │
         NLQ         AI Analyst     Dashboards
          │              │              │
          └──────────────┼──────────────┘
                         │
                 Semantic Query Engine
                         │
                  Safe join closure
                         │
             Governed tenant-aware data
```

Le moteur calcule automatiquement les tables intermédiaires requises pour un chemin de relation multi-hop. Les relations N:N restent interdites dans l'exécution automatique.

Le Dashboard Builder peut projeter après filtre les colonnes de la table de faits afin que les widgets physiques et les widgets sémantiques partagent le même contexte analytique.


## Collaboration & Review v2.6

Le Review Center s'appuie sur le metadata store Enterprise :

```text
Workspace
  ├── review_items
  │     ├── owner
  │     ├── reviewer
  │     ├── resource snapshot
  │     └── workflow state
  ├── review_comments
  ├── review_events (append-only)
  ├── collaboration_notifications
  └── resource_certifications
```

Les transitions et certifications passent par RBAC et génèrent des événements d'audit.


## v2.7 — Ingestion gouvernée et refresh

La couche d'ingestion persistante s'ajoute au plan de contrôle Enterprise :

```text
External SQL → Data Connector → Connector Source → Refresh Run → Immutable Dataset Version
                                      │                 │
                                      │                 └→ observability / watermark / drift
                                      └→ scheduler → Redis job → tenant-aware worker
```

Les credentials sont chiffrés dans le metadata store. Le refresh est un lifecycle système autorisé à charger la version brute précédente afin de ne pas matérialiser un sous-ensemble RLS ; les consumers analytiques utilisent toujours la boundary gouvernée.


## v2.8 — Data Reliability Plane

La v2.8 ajoute un plan de contrôle transversal, séparé des moteurs analytiques :

```text
Sources / Uploads
      ↓
Immutable Dataset Versions
      ↓
Data Reliability Plane
  ├── Contracts
  ├── Distribution Drift
  ├── Reliability Events
  ├── Lineage Graph
  ├── Impact Analysis
  └── Publication Gate
      ↓
Statistics / ML / AI / Dashboards / Reports / Review
```

Le gate est fail-closed pour les contrats `block` : une nouvelle version doit être contrôlée explicitement avant certification ou export Enterprise. Les refresh et transformations gouvernées déclenchent automatiquement les contrats actifs de leur lignée.
