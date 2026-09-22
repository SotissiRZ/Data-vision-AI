## Livré — v2.81.6 Single Authentication Entry Point

- écran standard Connexion / Inscription comme unique porte d’entrée de l’interface web ;
- suppression du formulaire de connexion historique de Gouvernance & sécurité ;
- suppression du contournement frontend `local_dev_enabled` ;
- retour automatique à l’écran d’authentification lorsque la session expire.

## Livré — v2.81.3 Password Visibility & Development Test Account

- icône œil accessible sur les champs de mot de passe d’authentification ;
- compte test local `demo@datavision.local` / `DataVision8!` ;
- rôle admin dans un workspace de démonstration isolé ;
- compte démo limité à `development`/`test` et bloqué en production ;
- compte démo indépendant du cycle de création du premier owner.

## Livré — v2.81.1 First-run Authentication UX Hotfix

- Première configuration locale simplifiée sans secret visible.
- Mot de passe minimum produit : 8 caractères.
- Bootstrap distant réservé à la console serveur.

## Livré — v2.81.0 Security & Documentation Freeze

- authentification requise par défaut ;
- hardening des sessions et de l’exposition API ;
- correction des blocages CI dependency/typecheck/Rego/hygiene ;
- dossier documentaire de mise en production ;
- gate SECURITY_DOCUMENTATION_ACCEPTANCE.

# Roadmap d’exécution DataVision AI

## Livré — v2.80.0 Release Candidate

- gel fonctionnel déclaré et versionné ;
- installation Windows alignée dynamiquement sur le fichier `VERSION` ;
- chemin d'upgrade v2.79 → v2.80 avec sauvegarde avant migration et conservation des volumes ;
- doctor de configuration pour détecter secrets placeholders et paramètres invalides ;
- migration marker RC `2.80.0-001` ;
- workflow Release aligné sur l'intégralité des gates récents et des E2E RC/accessibilité ;
- gate `RELEASE_INSTALLATION_ACCEPTANCE` 8/8 ;
- packaging reproductible + vérification SHA-256 conservés comme condition de release.

Prochain jalon : **v3.0.0 — Production Stable**, uniquement après réception et vérification des preuves externes cibles/UAT requises.

## Livré — v2.79.0 Hardening & End-to-End Validation

- headers de sécurité API/frontend et HSTS conditionnel côté API ;
- migrations ordonnées par version et idempotence contrôlée ;
- backup/restore drill vérifié comme scénario critique ;
- sign-off production durci par SHA-256 et revalidation des pièces jointes ;
- waivers interdits dans le sign-off strict par défaut ;
- CI rendue exhaustive sur tous les gates récents ;
- E2E Release Candidate et accessibilité ajoutés au pipeline ;
- gate `RELEASE_CANDIDATE_ACCEPTANCE` 8/8 ;
- CDC maintenu honnêtement à 97,3 % : les preuves cible/UAT restent externes.

Prochain jalon : **v2.80 — Release Candidate** : gel fonctionnel, packaging final, check d'installation/upgrade et préparation des preuves externes de sign-off.

## Livré — v2.78.0 CDC Gap Closure

- plans produit et quotas runtime persistants ;
- entitlements sur les capacités Enterprise sensibles ;
- KMS cloud natif AWS KMS / Google Cloud KMS / Azure Key Vault ;
- causalité observationnelle gouvernée avec `causal_claim_allowed=false` ;
- scheduler proactif persistant et claim sûr multi-worker ;
- gate `CDC_GAP_CLOSURE_ACCEPTANCE` 8/8 ;
- CDC porté à 97,3 % : 71 implemented, 4 partial, 0 missing.

Les gaps restants ne sont pas masqués : §2 est une frontière de parité d’écosystème, tandis que §71/§74 nécessitent des preuves de cible et une UAT signée; §75 dépend de ces clôtures.

Prochain jalon : **v2.79 — Hardening & End-to-End Validation** : stress des parcours critiques, matrice E2E de release candidate, sécurité/résilience et préparation du sign-off externe.

## Livré — v2.77.0 Performance & SLO Evidence

- policy-as-code versionnée pour les budgets performance/SLO ;
- benchmark local de non-régression ;
- runner de charge externe concurrent pour cible HTTPS réelle ;
- p50/p95/p99, débit, erreurs et volume mesurés ;
- validation SHA-256 et contraintes minimales de charge ;
- ledger de preuves par workspace et séparation stricte local/production ;
- cockpit Operational Intelligence enrichi ;
- gate `PERFORMANCE_SLO_ACCEPTANCE` 8/8 ;
- CDC §59 fermé.

Prochain jalon : **v2.78 — CDC Gap Closure** : fermer les gaps restants P0/P1/P2 techniquement automatisables, puis préparer le Release Candidate sans falsifier les preuves externes d'UAT/déploiement.

## Livré — v2.76.0 Workspace Environments & Reproducibility

- manifests Python/R gouvernés par workspace ;
- overlay notebook avec fusion déterministe des dépendances ;
- locks exacts issus de l'image sandbox approuvée ;
- empreintes SHA-256 workspace et notebook effectif ;
- détection de dérive et vérification de reproductibilité ;
- invalidation des kernels lors des changements de manifest ;
- provenance des runs enrichie ;
- gate `WORKSPACE_ENVIRONMENT_ACCEPTANCE` 8/8 ;
- CDC §40 et §41 fermés.

Prochain jalon : **v2.77 — Performance & SLO Evidence** : benchmarks reproductibles, budgets de latence/charge et preuves SLO automatisées pour fermer le gap §59 sans inventer de résultats production.

## Livré — v2.75.0 Cloud Connectors & CDC ingestion

- object storage S3/S3-compatible, Google Cloud Storage et Azure Blob ;
- découverte cloud et ingestion CSV/JSON/JSONL/Parquet/XLSX ;
- sources CDC log-based avec enveloppes Debezium/canoniques ;
- clés primaires explicites, déduplication, checkpoints par partition et replay idempotent ;
- schema drift, lineage et matérialisation en versions immuables ;
- dry-run et endpoints gouvernés `connectors:read` / `refresh:run` ;
- gate `CLOUD_CDC_ACCEPTANCE` 8/8 ;
- CDC §69 fermé.

Prochain jalon : **v2.76 — Workspace Environments & Reproducibility** : environnements Python/R gouvernés, manifests reproductibles et isolation par workspace sans installation arbitraire dans le runtime principal.

## Livré — v2.74.0 Internationalisation & accessibilité foundations

- quatre locales : français, anglais, espagnol et arabe ;
- catalogues à parité de clés avec fallback déterministe ;
- persistance locale + profil Entreprise ;
- `lang` / `dir` dynamiques et RTL arabe ;
- skip-link, focus management, landmarks et annonces `aria-live` ;
- contraste renforcé, focus visible et réduction des animations ;
- test navigateur Playwright + gate `I18N_ACCESSIBILITY_ACCEPTANCE` 8/8 ;
- CDC §64 et §65 fermés.

Jalon **v2.75 — Cloud Connectors & CDC ingestion** livré : object storage cloud, CDC checkpointé, reprise et matérialisation immuable.

## Livré — v2.73.0 Model Gateway multi-provider natif

- Anthropic Messages API natif ;
- Gemini `models.generateContent` natif ;
- JSON Schema structuré sur les deux adapters ;
- Secret Vault / env credentials gouvernés ;
- routage confidentialité, fallback, budgets et télémétrie conservés ;
- Centre de contrôle IA étendu ;
- `MODEL_GATEWAY_ACCEPTANCE` 8/8 et CDC §48 fermé.

## Livré — v2.72.0 Data Storytelling avancé

- narration analytique multi-page déterministe et structurée ;
- audience, objectif, ton et longueur pilotables ;
- claims systématiquement liés à des preuves vérifiables ;
- mesure de couverture de preuve et validation de cohérence ;
- export multi-format et aperçu de trame ;
- publication gouvernée avec reçu immuable et contrôle du Data Reliability Gate ;
- gate `STORYTELLING_ACCEPTANCE 8/8`.

Jalon **v2.73 — Model Gateway multi-provider** livré : adaptateurs natifs Anthropic/Gemini, sorties structurées, gouvernance, Secret Vault, routage et audit.

Jalon **v2.74 — Internationalisation & accessibilité foundations** livré : i18n 4 langues, RTL, préférences persistées, navigation clavier/focus et gate accessibilité.

## Livré — v2.71.0 AI Data Quality & remédiation guidée

- recommandations déterministes contextualisées sur les problèmes réellement détectés ;
- preview avant/après sans mutation du dataset ;
- sélection utilisateur explicite et niveau de risque visible ;
- application gouvernée vers une nouvelle version immuable ;
- Assistant connecté au planner de remédiation qualité ;
- gate `QUALITY_REMEDIATION_ACCEPTANCE 8/8`.

Prochain jalon : **v2.72 — Data Storytelling avancé** : narration analytique multi-page, structure automatique, preuves liées et publication gouvernée.

## Livré — v2.70.0 AutoML Forecasting + Anomaly unifié

- forecasting et anomalies intégrés au même moteur d'expériences AutoML ;
- validation rolling-origin stricte pour les séries temporelles ;
- sélection non supervisée des détecteurs par robustesse, sans pseudo-ground-truth ;
- artefacts spécialisés et Model Cards compatibles avec le Model Registry ;
- interface et Assistant alignés sur le workflow AutoML unifié ;
- gate `AUTOML_UNIFIED_ACCEPTANCE 8/8`.

Jalon livré en **v2.71.0** : AI Data Quality & remédiation guidée.

## Livré — v2.69.0 Visual Analytics & NL→Viz avancé

- recommandations scorées et explicables ;
- couverture homogène des visualisations avancées du CDC ;
- édition conversationnelle de visualisations existantes ;
- compositions multi-graphiques automatiques ;
- assistant et Visualization Studio alignés sur le même moteur backend.

Prochain jalon : v2.70 — AutoML Forecasting + Anomaly unifié.

# Roadmap d’exécution

## Livré — v2.68.0 Connecteurs, Data Catalog & Lineage

- import ZIP natif multi-datasets sécurisé ;
- retries/backoff exponentiels configurables pour les connecteurs ;
- discovery/catalogue unifié des actifs data ;
- documentation métier, ownership, stewardship, tags et certification ;
- lineage cross-system depuis le système source jusqu'aux consommateurs ;
- gate `CATALOG_LINEAGE_ACCEPTANCE 8/8`.

La prochaine priorité est **v2.69 — Visual Analytics & NL→Viz avancé** : couverture homogène de la bibliothèque de graphiques, édition conversationnelle et compositions multi-visuelles.

## Livré — v2.63.0 Sécurité opérationnelle & supply chain

- SBOM CycloneDX/SPDX indexés et provenance in-toto/SLSA ;
- signatures keyless Sigstore/Cosign des artefacts et images ;
- images GHCR avec provenance/SBOM BuildKit ;
- policy-as-code Rego bloquante sur les manifests Kubernetes ;
- rotation automatique bornée aux secrets explicitement générés ;
- rollback de release en deux phases et drill non destructif ;
- CronJob Kubernetes de rotation désactivé par défaut ;
- gate `SUPPLY_CHAIN_ACCEPTANCE 8/8`.

La prochaine priorité est **v2.64 — Admission, runtime security & conformité continue** : admission policies signées, vérification d’images à l’entrée du cluster, profils seccomp/AppArmor, détection runtime et evidence packs de conformité.

## Livré — v2.62.0 Observabilité distribuée & opérations multi-cluster

- propagation W3C `traceparent` et corrélation par trace ID ;
- pipeline OpenTelemetry traces avec export OTLP HTTP optionnel ;
- AlertmanagerConfig multi-canaux Slack / webhook / email ;
- réplication cross-region vérifiée par SHA-256 distant ;
- control plane multi-cluster persistant ;
- bascule contrôlée en deux phases avec préflight et jeton temporaire ;
- runbooks SRE exécutables ;
- gate `DISTRIBUTED_OPS_ACCEPTANCE 8/8`.

## Livré — v2.60.0 Exploitation avancée & SRE

- budgets d’erreur calculés sur les SLO réels ;
- alertes SRE persistées et routables via Governed Actions ;
- stockage objet S3-compatible signé SigV4 pour les backups ;
- manifest backup v2 et restore drills non destructifs automatisés ;
- autoscaling worker KEDA/Redis optionnel en complément du HPA CPU ;
- chaos contrôlé désactivé par défaut et borné à des probes SRE ;
- cockpit Operational Intelligence enrichi ;
- gate `SRE_ACCEPTANCE 8/8`.

## Livré — v2.61.0 SRE automatisé & continuité multi-zone

- recording rules et alert rules Prometheus packagées ;
- dashboard Grafana SRE/SLO livré avec le chart Helm ;
- routage des alertes SRE par workspace, sévérité et code ;
- réplication de sauvegardes multi-cibles S3 avec audit par cible ;
- exercices DR orchestrés, restore drill et fault model non destructif ;
- gate `SRE_AUTOMATION_ACCEPTANCE 8/8`.

La prochaine priorité est **v2.62 — Observabilité distribuée & opérations multi-cluster** : traces corrélées, Alertmanager/notifications multi-canaux, réplication cross-region vérifiée, runbooks exécutables et orchestration de bascule contrôlée.

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

## v2.64 — Admission, runtime security & conformité continue — livré

- admission Kyverno cluster-wide opt-in ;
- vérification d'images signées Sigstore/Cosign configurable ;
- contexte runtime non-root / seccomp RuntimeDefault / drop ALL / no privilege escalation ;
- règles Falco packagées sans imposer l'installation de Falco ;
- scans de conformité avec distinction entre configuration déclarée et observation réelle ;
- journal d'événements runtime ;
- evidence packs SHA-256 ;
- CronJob de conformité et contrôle de dérive ;
- politique Rego étendue aux garde-fous runtime.

## v2.65 — Conformité réglementaire automatisée & posture consolidée — livré

- catalogue de contrôles et mappings NIST/ISO/SOC 2 ;
- historique de posture, exceptions gouvernées, evidence packs et remédiation proposal-only.

## v2.66 — Production Acceptance & E2E — livré

- frontend typecheck/build bloquants en CI ;
- Docker Compose config + stack candidate réelle ;
- Helm lint/render + policy-as-code ;
- Playwright smoke/MVP/production ;
- smoke de charge p95/error rate ;
- registre de preuves et sign-off cible sans faux positif ;
- runner Windows reproductible pour Docker Desktop.

Prochain jalon : v2.67 — Notebook Runtime persistant Python/R, kernels et environnements par projet.
