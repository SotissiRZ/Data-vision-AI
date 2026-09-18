# Roadmap d'exécution — après v2.2.0

## Implémenté

Le socle local couvre maintenant : import et profiling, qualité, préparation versionnée, lineage/pipelines, statistiques descriptives et inférentielles, régression/ANOVA/ACP/clustering, Visualization Studio, SQL/NLQ, AutoML, forecasting, anomalies, XAI core, AI Analyst/Critic, Dashboard Builder, Report Intelligence, couche sémantique v1, Metric Pulse, Trust Center et Decision Lab.

L'interface v2 est organisée par **workflow** plutôt que par liste exhaustive de modules.

## P0 — fiabilité Enterprise

Implémenté en v2.1 :

- authentification locale signée ;
- organisations et workspaces ;
- PostgreSQL metadata store + fallback SQLite ;
- RBAC sur les nouvelles ressources Enterprise ;
- registre RLS/permissions colonnes + governed preview ;
- audit log consolidé ;
- jobs asynchrones Redis Worker ;
- suivi des jobs et annulation des jobs en file.

À terminer :

- OIDC/SSO et refresh tokens ;
- enforcement tenant-aware/RLS/CLS sur toutes les routes analytiques historiques ;
- secrets chiffrés / vault ;
- annulation préemptive d'un job en cours ;
- limites de ressources et sandbox renforcée ;
- tests E2E Docker/Next.js automatisés dans CI.

## P1 — Semantic Layer v2

- relations multi-tables ;
- métriques calculées et métriques dérivées ;
- hiérarchies ;
- time intelligence / calendrier ;
- validation de formules ;
- workflow d'approbation/certification ;
- règles de sécurité sémantiques ;
- import/export de définitions.

## P1 — Proactive Analytics

- scheduler ;
- alertes sur seuil / variation / anomalie ;
- abonnements/digests ;
- règles par audience ;
- webhooks ;
- historique des alertes et acquittement.

## P1 — Action Layer

- actions externes avec permissions : webhook, Slack/Teams, ticketing, CRM et APIs métier ;
- prévisualisation de l'action ;
- approbation humaine obligatoire pour les actions sensibles ;
- journal d'exécution et rollback lorsque le système cible le permet.

## P1 — AI Gateway

- fournisseurs OpenAI-compatible / Anthropic-compatible / Gemini / Ollama ;
- consentement explicite avant transfert de données ;
- politiques de rétention ;
- redaction/sampling contextuel ;
- traces, tokens, coûts et latence ;
- evals/golden datasets ;
- fallback local.

## P2 — Data Science & Causal

- notebook Python/R/SQL ;
- R Workspace complet ;
- SHAP complet ;
- fairness avancée ;
- causal inference séparée du what-if prédictif ;
- optimisation sous contraintes ;
- survival analysis, géospatial et plugins spécialisés.

## P2 — Collaboration & distribution

- commentaires, mentions et validation ;
- partage de dashboards/rapports ;
- connecteurs bases/cloud ;
- plugin/MCP runtime avec permissions ;
- packaging desktop natif ;
- Kubernetes/SSO/SLA pour Enterprise.
