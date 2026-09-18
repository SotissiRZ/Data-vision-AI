# Roadmap d'exécution — après v2.8.0

## État actuel

DataVision dispose maintenant d'un runtime sémantique multi-tables, d'une Inbox proactive, d'une gouvernance Enterprise, de connecteurs SQL versionnés et d'une couche Data Reliability capable de bloquer la publication d'une version non conforme.

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

## v2.8 — Data Reliability & Lineage — livré

- data contracts explicites ;
- tests de schéma, volume, nullité, unicité et plage ;
- détection de rupture de distribution ;
- lineage source → dataset → semantic metric → dashboard/report/model ;
- impact analysis avant changement ;
- blocage de publication en cas de contrat critique rompu ;
- freshness et quality SLO au niveau data product.

Reste à compléter : lineage cross-system, contrats SQL personnalisés, drift multivarié, notifications externes et SLO historiques agrégés.

## v2.9 — Observability, Evaluation & Operational Intelligence

- observabilité structurée des requêtes, jobs, agents et modèles ;
- latence / coût / tokens / tool failures pour les appels IA ;
- dataset d’évaluation des agents avec expected SQL/result/chart ;
- scoring exactitude / sécurité / reproductibilité ;
- data-product SLO et historique de fiabilité ;
- alertes et notifications sortantes gouvernées ;
- retry/backoff des jobs et connecteurs ;
- usage analytics pour identifier les fonctionnalités réellement utilisées.


## v3 — Enterprise Analytics Platform

- SSO/OIDC ;
- semantic cache distribué ;
- object storage S3-compatible ;
- Kubernetes optionnel ;
- private AI ;
- plugin/MCP runtime avec permissions ;
- lineage cross-system ;
- SLA et observabilité avancée.
