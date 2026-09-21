# Roadmap d’exécution

## Livré — v2.60.0 Exploitation avancée & SRE

- budgets d’erreur calculés sur les SLO réels ;
- alertes SRE persistées et routables via Governed Actions ;
- stockage objet S3-compatible signé SigV4 pour les backups ;
- manifest backup v2 et restore drills non destructifs automatisés ;
- autoscaling worker KEDA/Redis optionnel en complément du HPA CPU ;
- chaos contrôlé désactivé par défaut et borné à des probes SRE ;
- cockpit Operational Intelligence enrichi ;
- gate `SRE_ACCEPTANCE 8/8`.

La prochaine priorité est **v2.61 — SRE automatisé & continuité multi-zone** : dashboards/recording rules Prometheus packagés, alert routing enrichi, réplication de sauvegardes multi-cibles, exercices DR orchestrés et tests de perte de dépendance en environnement de staging.

## Livré — v2.59.0 Résilience & exploitation HA

- probes startup/readiness/liveness distinctes ;
- PodDisruptionBudget et autoscaling HPA ;
- rolling updates et répartition multi-nœuds ;
- migrations de schéma versionnées et Job Helm pré-upgrade ;
- sauvegarde/restauration vérifiée SHA-256 et CronJob planifié ;
- rotation KMS Vault Transit opérable et auditée ;
- runbook de reprise après sinistre avec RPO/RTO ;
- gate `RESILIENCE_ACCEPTANCE 8/8`.

Cette priorité est livrée en **v2.60.0**.

## Livré — v2.58.0 Hardening de production Entreprise

- KMS/HSM externe via Vault Transit ;
- SCIM Groups avec cycle de vie et mapping de rôles ;
- politiques organisationnelles de session/appareil et appareils approuvés ;
- OpenTelemetry Collector avec scrape Prometheus interne protégé ;
- packaging Kubernetes/Helm optionnel ;
- Docker Compose conservé ;
- gate `HARDENING_ACCEPTANCE 8/8`.

La prochaine priorité est **v2.59 — Résilience & exploitation HA** : probes avancées, PodDisruptionBudget, autoscaling, migrations de schéma explicites, sauvegarde/restauration, rotation KMS opérable et runbooks de reprise.

## Livré — v2.57.0 Fenêtre d’assistant dynamique

- assistant flottant redimensionnable manuellement ;
- tailles compacte, normale et agrandie ;
- dimensions persistées localement ;
- bornes dynamiques selon le viewport ;
- reflow interne pour les faibles largeurs ;
- accessibilité reduced-motion ;
- gate `ASSISTANT_WINDOW_ACCEPTANCE 6/6`.

La consolidation **Hardening de production Entreprise** est décalée en **v2.58** : KMS/HSM externe, SCIM Groups, politiques de session/appareil, OpenTelemetry collector et packaging Kubernetes/Helm.

## Livré — v2.56.0 Plateforme Entreprise

- terminologie produit normalisée sur **Entreprise** ;
- SSO OIDC conservé et complété par la découverte IdP selon le domaine email ;
- MFA WebAuthn intégré à la posture de sécurité ;
- provisioning SCIM 2.0 avec jetons stockés uniquement sous forme SHA-256 ;
- cycle SCIM utilisateurs : création, lecture, changement de rôle et désactivation ;
- Private AI strict appliqué par le moteur de politiques IA existant ;
- profil on-prem et egress externe en opt-in explicite ;
- métriques Prometheus authentifiées et isolées par workspace ;
- cockpit de posture Entreprise ;
- gate `ENTREPRISE_ACCEPTANCE 8/8`.

La prochaine consolidation cible **v2.58 — Hardening de production Entreprise** : KMS/HSM externe, SCIM Groups, politiques de session/appareil, OpenTelemetry collector et packaging Kubernetes/Helm sans régression du mode Docker Compose.

## Livré — v2.44 Assistant V1 contextuel et tool-connected

- bouton flottant global ;
- contexte live écran / dataset / version / modèle ;
- tool registry filtré aux capacités réellement exécutables ;
- exécution sur moteurs DataVision réels avec RBAC ;
- confirmation/refus/reprise des actions gouvernées ;
- resynchronisation UI après actions ;
- fichiers + texte + voix ;
- gate `ASSISTANT_ACCEPTANCE` 8/8.

La prochaine priorité produit est **v2.45 — Assistant multimodal/proactif : voix enrichie, fichiers avancés, erreurs et aide proactive**.

## Livré — v2.43 Data Workspace reproductible

- SQL local read-only ;
- notebooks Python / SQL / R ;
- sandbox Python/R isolé ;
- liaison explicite aux versions immuables de datasets ;
- exécution ordonnée de tout le notebook ;
- provenance renforcée et fingerprints SHA-256 ;
- artefacts persistés et promotion contrôlée vers une nouvelle version de dataset ;
- gate `WORKSPACE_ACCEPTANCE` 8/8.

La priorité v2.44 a été livrée ; voir la section ci-dessus.

## Livré — v2.12 Identity, SSO & Secret Management

Sessions persistantes révocables, refresh tokens rotatifs, SSO OIDC Authorization Code + PKCE, vérification RS256/JWKS, provisioning JIT et coffre de secrets versionné sont maintenant implémentés. Le coffre supporte stockage local chiffré, références environnement et HashiCorp Vault KV v2.

La prochaine priorité est **v2.13 — Entreprise Administration & Identity Lifecycle** : SCIM 2.0, politiques de session/appareil, routage IdP par organisation/domaine, MFA/WebAuthn optionnel, intégration KMS externe et événements de sécurité consolidés.

## Livré — v2.11 Entreprise Action Connectors
Slack, Teams, Jira, Email SMTP, webhook générique, credentials chiffrés, OAuth2 client credentials et approbations multi-étapes sont implémentés.


## État actuel

DataVision dispose maintenant d'un runtime sémantique multi-tables, d'une Inbox proactive, d'une gouvernance Entreprise, de connecteurs SQL versionnés, d'une couche Data Reliability capable de bloquer la publication d'une version non conforme et d'un cockpit d'observabilité/évaluation pour mesurer SLO, usage réel et non-régression de l'AI Analyst.

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

Complété en v2.54.0 : WebSocket workspace-scoped, diff visuel des snapshots, équipes, partage gouverné et notifications sortantes via Governed Actions.

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


## v3 — Entreprise Analytics Platform

- fédération d’identité avancée / SCIM ;
- semantic cache distribué ;
- object storage S3-compatible ;
- Kubernetes optionnel ;
- private AI ;
- plugin/MCP runtime avec permissions ;
- lineage cross-system ;
- SLA et observabilité avancée.

Complété en v2.55.0 : Governance Control Plane, matrice RBAC/RLS/CLS effective, snapshots et readiness de publication.
