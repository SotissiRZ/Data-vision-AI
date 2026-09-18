# DataVision AI v2.9 — Operational Intelligence

## Objectif

La v2.9 rend l’exploitation de DataVision mesurable. Le système doit pouvoir répondre à quatre questions : la plateforme est-elle disponible, les jobs sont-ils fiables, quelles fonctions sont réellement utilisées et l’AI Analyst conserve-t-il ses comportements attendus après modification du code ou du modèle sémantique ?

## 1. Télémétrie

La table `telemetry_events` reçoit des événements HTTP, jobs et évaluations. L’instrumentation HTTP est best-effort : une panne du metadata store d’observabilité ne doit pas faire échouer la requête utilisateur.

Champs principaux : `event_kind`, `feature`, `name`, `status`, `latency_ms`, `input_tokens`, `output_tokens`, `estimated_cost_usd`, `resource_type`, `resource_id`, contexte tenant et metadata JSON.

Les tokens/coûts restent nuls lorsqu’aucun fournisseur externe instrumenté ne les fournit. DataVision ne les estime pas artificiellement.

## 2. SLO

Le endpoint `GET /api/v1/workspaces/{workspace_id}/operational/overview` calcule sur une fenêtre temporelle :

- disponibilité HTTP ;
- p50 / p95 / p99 ;
- taux de succès des jobs ;
- jobs en `retry_wait` ;
- taux de succès des refresh ;
- dernier score d’évaluation ;
- consommation LLM instrumentée ;
- fonctionnalités les plus utilisées.

Les seuils v2.9 sont des objectifs internes visibles dans l’UI, pas des garanties contractuelles.

## 3. Usage analytics

Les routes sont regroupées par feature : AI Analyst, NLQ, SQL Workspace, Semantic Layer, Dashboards, Reports, AutoML, Models & XAI, Forecasting, Statistical Analysis, Visualization Studio, Proactive Intelligence, Reliability, Lineage, Connectors, Sources & Refresh, Collaboration & Review et Data Workspace.

L’objectif est de prioriser les améliorations à partir de l’usage observé.

## 4. AI Evaluation Lab

Une suite contient des cas reproductibles liés à un dataset. Les attentes supportées sont :

- `expected_intent` ;
- `critic_status` ;
- `required_tools` ;
- `answer_contains` ;
- `min_findings` ;
- `max_duration_ms` ;
- `expected_value_path`, `expected_value`, `tolerance`.

Le run applique le contexte tenant-aware avant de charger le dataset et réutilise `analyze_dataset()`. Les checks sont déterministes et persistés dans `evaluation_results`.

## 5. Retry / backoff

Chaque job stocke sa politique dans `_job_options`. En cas d’échec, DataVision :

1. enregistre la tentative dans `job_attempts` ;
2. calcule le backoff exponentiel ;
3. place le job dans `datavision:jobs:retry` avec son timestamp d’échéance ;
4. le worker remet les jobs échus dans la queue principale sans dormir pendant le backoff ;
5. marque définitivement le job `failed` quand les retries sont épuisés.

L’annulation d’un job en `retry_wait` retire aussi son entrée du sorted set. Les valeurs `max_retries` et `retry_backoff_seconds` sont configurables depuis le formulaire Jobs asynchrones du Governance Center.

## 6. UI

`Gouverner → Observabilité & Eval` regroupe :

- scorecards API/jobs/refresh/evaluation ;
- bandeau SLO ;
- classement des features ;
- tokens/coûts instrumentés ;
- Evaluation Lab ;
- télémétrie récente.

L’interface suit l’architecture professionnelle v2 : hiérarchie claire, détails progressifs et séparation entre santé opérationnelle et configuration de gouvernance.
