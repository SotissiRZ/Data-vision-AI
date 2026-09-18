# Roadmap d'exécution

## Livré — v2.12 Identity, SSO & Secret Management

Sessions persistantes révocables, refresh tokens rotatifs, SSO OIDC Authorization Code + PKCE, vérification RS256/JWKS, provisioning JIT et coffre de secrets versionné sont maintenant implémentés. Le coffre supporte stockage local chiffré, références environnement et HashiCorp Vault KV v2.

La prochaine priorité est **v2.13 — Enterprise Administration & Identity Lifecycle** : SCIM 2.0, politiques de session/appareil, routage IdP par organisation/domaine, MFA/WebAuthn optionnel, intégration KMS externe et événements de sécurité consolidés.

## Livré — v2.11 Enterprise Action Connectors
Slack, Teams, Jira, Email SMTP, webhook générique, credentials chiffrés, OAuth2 client credentials et approbations multi-étapes sont implémentés.


## État actuel

DataVision dispose maintenant d'un runtime sémantique multi-tables, d'une Inbox proactive, d'une gouvernance Enterprise, de connecteurs SQL versionnés, d'une couche Data Reliability capable de bloquer la publication d'une version non conforme et d'un cockpit d'observabilité/évaluation pour mesurer SLO, usage réel et non-régression de l'AI Analyst.

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

## v2.9 — Observability, Evaluation & Operational Intelligence — livré

- télémétrie HTTP/jobs/evaluations par workspace ;
- p50/p95/p99, disponibilité API, job success et refresh success ;
- usage analytics par feature ;
- schéma tokens/coûts provider-aware sans estimation fictive ;
- suites de non-régression AI Analyst ;
- attentes déterministes : intent, Critic, tools, texte, findings, durée et valeur/tolérance ;
- scoring et historique des evaluation runs ;
- retry/backoff exponentiel Redis sans blocage du worker ;
- historique des tentatives de jobs ;
- cockpit Observabilité & Eval.

Reste à compléter : OpenTelemetry/Prometheus externe, coût provider-native complet, alertes sortantes gouvernées et tests expected SQL/chart dédiés.

## v2.10 — Governed Actions & Automation — livré

- règles événementielles à partir de Reliability, Proactive Inbox et SLO ;
- actions sortantes gouvernées avec approbation ;
- webhooks signés et destinations configurables ;
- Slack/Teams/email via connecteurs optionnels ;
- calendrier de scans proactifs ;
- déduplication, throttling et quiet hours ;
- journal complet des actions et replay contrôlé.


## v3 — Enterprise Analytics Platform

- fédération d’identité avancée / SCIM ;
- semantic cache distribué ;
- object storage S3-compatible ;
- Kubernetes optionnel ;
- private AI ;
- plugin/MCP runtime avec permissions ;
- lineage cross-system ;
- SLA et observabilité avancée.
