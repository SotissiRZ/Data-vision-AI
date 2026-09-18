# Roadmap d'exécution — après v2.5.0

## État actuel

DataVision dispose maintenant d'un runtime sémantique multi-tables relié au NLQ, à AI Analyst et aux dashboards, ainsi que d'une Inbox analytique proactive avec surveillance persistante des métriques.

## v2.5 — Proactive Intelligence — livré

- watches sur métriques certifiées ;
- règles de seuil et anomalies temporelles ;
- alertes persistées et dédupliquées ;
- Inbox analytique ;
- contexte explicatif et provenance ;
- investigations recommandées ;
- job asynchrone `proactive_scan`.

Reste à compléter : scheduler calendaire et actions sortantes gouvernées.

## v2.6 — Collaboration & Review

- commentaires sur métriques, analyses et dashboards ;
- workflow draft / review / approved ;
- certification avec propriétaire et date d'expiration ;
- mentions et approbations ;
- historique de décisions.

## v2.7 — Connectors & Refresh

- PostgreSQL / MySQL de production ;
- refresh planifié ;
- incremental refresh ;
- observabilité des connecteurs ;
- gestion des secrets par fournisseur.

## v3 — Enterprise Analytics Platform

- SSO/OIDC ;
- semantic cache distribué ;
- object storage S3-compatible ;
- Kubernetes optionnel ;
- private AI ;
- plugin/MCP runtime avec permissions ;
- lineage cross-system ;
- SLA et observabilité avancée.
