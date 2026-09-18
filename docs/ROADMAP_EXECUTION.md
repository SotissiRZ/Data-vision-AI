# Roadmap d'exécution — après v2.7.0

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

## v2.6 — Collaboration & Review — livré

- commentaires sur métriques, analyses, dashboards, rapports et modèles ;
- workflow draft / in review / approved / changes requested ;
- ownership et reviewer ;
- mentions et notifications ;
- certification avec propriétaire et date d'expiration ;
- historique append-only des décisions.

Reste à compléter : temps réel WebSocket, diff visuel des versions et notifications sortantes gouvernées.

## v2.7 — Connectors & Refresh — livré

- PostgreSQL / MySQL ;
- credentials chiffrés au repos ;
- découverte de schéma ;
- refresh manuel et planifié ;
- incremental refresh avec watermark ;
- freshness SLA ;
- schema drift ;
- observabilité et historique des refresh.

Reste à compléter : secret manager externe, CDC log-based, retry/backoff et connecteurs cloud.

## v2.8 — Data Reliability & Lineage

- data contracts explicites ;
- tests de schéma, volume, nullité, unicité et plage ;
- détection de rupture de distribution ;
- lineage source → dataset → semantic metric → dashboard/report/model ;
- impact analysis avant changement ;
- blocage de publication en cas de contrat critique rompu ;
- freshness et quality SLO au niveau data product.

## v3 — Enterprise Analytics Platform

- SSO/OIDC ;
- semantic cache distribué ;
- object storage S3-compatible ;
- Kubernetes optionnel ;
- private AI ;
- plugin/MCP runtime avec permissions ;
- lineage cross-system ;
- SLA et observabilité avancée.
