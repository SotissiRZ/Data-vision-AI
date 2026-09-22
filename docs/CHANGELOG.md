# Changelog

## 2.81.6 — Single Authentication Entry Point

- suppression du formulaire de connexion historique intégré à **Gouvernance & sécurité** ;
- l’écran standard **Connexion / Inscription** devient l’unique porte d’entrée de l’interface web ;
- suppression du contournement frontend lié à `local_dev_enabled` : même en développement, l’interface demande une session ;
- Gouvernance réutilise exclusivement la session DataVision existante et ne redemande plus les identifiants ;
- en cas de session expirée, les jetons locaux sont nettoyés et l’application retourne vers l’écran d’authentification standard ;
- le SSO, le MFA, le compte de démonstration et l’auto-inscription restent accessibles depuis l’écran d’authentification unique.

## 2.81.5 — Standard Login / Sign-up Authentication

- Écran d’authentification standard à deux modes : **Connexion** et **Inscription**.
- Bascule immédiate dans les deux sens sans quitter la page.
- Nouvel endpoint `POST /api/v1/auth/register` pour l’auto-inscription multi-tenant.
- Chaque inscription crée une organisation et un workspace isolés dont l’utilisateur est propriétaire.
- `SELF_REGISTRATION_ENABLED` permet de désactiver l’inscription libre sans désactiver la connexion.
- Le bootstrap sécurisé de première installation reste disponible lorsque l’auto-inscription est désactivée.
- Le compte de démonstration local et les mécanismes MFA/SSO existants sont conservés.

## 2.81.4 — Windows Preflight Runtime Isolation Hotfix

- correction du préflight Windows qui exécutait certains tests `pytest` avec le Python global de Windows ;
- suppression de cette dépendance implicite aux paquets backend installés sur l’hôte (`pydantic-settings`, FastAPI, SQLAlchemy, etc.) ;
- les contrôles pré-build locaux valident désormais les manifests, fichiers et contrats statiques sans importer l’application backend ;
- ajout d’un smoke test Python **dans l’image API fraîchement construite** avant migration/démarrage ;
- l’upgrade échoue désormais proprement si l’image conteneurisée ne contient pas `pydantic_settings`, `fastapi`, `sqlalchemy` ou `cryptography` ;
- aucun `pip install` backend n’est requis sur Windows pour installer ou mettre à jour DataVision.

## 2.81.3 — Authentication Recovery & Scrypt Memory Hotfix

- correction de l’erreur OpenSSL `[digital envelope routines] memory limit exceeded` lors du hachage scrypt avec `N=131072` grâce à un budget mémoire explicite et configurable ;
- ajout de `PASSWORD_SCRYPT_MAXMEM_MB=256` avec marge calculée à partir du coût scrypt ;
- compte test activé par défaut en développement et créé automatiquement s’il n’existe pas, tout en restant forcé hors service en production ;
- ajout d’une alternative **Vous avez déjà un compte ? Se connecter** directement depuis la première configuration ;
- retour possible vers **Configurer DataVision** depuis l’écran de connexion tant que le premier propriétaire n’est pas créé ;
- maintien de l’icône œil sur les champs de mot de passe et du minimum de 8 caractères ;
- tests de non-régression ajoutés pour le coût scrypt par défaut, le compte test et le basculement configuration/connexion.
- suppression automatique de l’ancienne variable inutilisée `BOOTSTRAP_SECRET` lors de l’installation ou de l’upgrade Windows.

## 2.81.2 — Password Visibility & Development Test Account

- ajout d’une icône œil accessible sur les champs de mot de passe de connexion, première configuration et provisionnement des membres ;
- ajout d’un compte test local `demo@datavision.local` avec mot de passe `DataVision8!` et rôle `admin` ;
- bouton de connexion automatique au compte test sur l’écran d’authentification ;
- compte test configurable par variables d’environnement et strictement limité à `development`/`test` ;
- compte test impossible à provisionner en production, même si l’option est activée par erreur ;
- le compte test ne bloque pas la création du premier propriétaire ;
- documentation, contrôles de configuration, gates sécurité et tests mis à jour.

## 2.81.1 — First-run Authentication UX Hotfix

- suppression du champ `BOOTSTRAP_SECRET` de l'interface utilisateur ;
- assistant de première configuration local : nom, email, organisation, mot de passe et confirmation ;
- session d'initialisation interne aléatoire, courte, HttpOnly et `SameSite=Strict` ;
- verrouillage automatique du bootstrap dès que le premier propriétaire existe ;
- bootstrap navigateur refusé sur une instance distante ; création serveur disponible via `python -m app.ops.bootstrap_owner` ;
- longueur minimale du mot de passe fixée à 8 caractères ; scrypt renforcé conservé ;
- documentation, gates et tests mis à jour ;
- restauration des preuves `docs/data/` requises par les gates production ;
- `repository_hygiene` tolère un `.env` local non versionné tout en refusant un `.env` suivi par Git.

## 2.81.0 — Security & Documentation Freeze

- authentification obligatoire par défaut (`AUTH_MODE=required`) ;
- mode anonyme limité à `local_dev` hors production ;
- throttling login + bootstrap production protégé ;
- tokens navigateur limités à `sessionStorage` ;
- OpenAPI désactivé par défaut ;
- correction conflit `boto3`/Redshift, TypeScript CI et Rego Conftest ;
- documents technique, utilisateur, déploiement, sécurité et exploitation ;
- outil de nettoyage des fichiers legacy après extraction superposée.

## 2.80.0 — Release Candidate

- gel fonctionnel et policy RC versionnée ;
- correction des dérives de version dans les scripts Windows ;
- ajout d'un upgrade Windows sauvegardé, migré et vérifié sans `down -v` ;
- ajout d'un doctor de configuration local/production ;
- workflow Release rendu exhaustif sur les gates récents et les E2E accessibilité/RC ;
- migration marker `2.80.0-001` ;
- gate `RELEASE_INSTALLATION_ACCEPTANCE` 8/8 ;
- maintien explicite des preuves externes UAT/cible en attente.

## 2.79.0 — Hardening & End-to-End Validation

- sécurité HTTP durcie sur API et frontend ;
- ordre des migrations indépendant de l'ordre de déclaration ;
- migration marker 2.79 et validation idempotente ;
- backup/restore drill dans la matrice RC ;
- sign-off de production avec hash des preuves et pièces jointes revérifiées ;
- waivers refusés par défaut en sign-off strict ;
- CI complétée avec tous les gates v2.71→v2.79 ;
- E2E accessibilité + release candidate exécutés en CI ;
- gate `RELEASE_CANDIDATE_ACCEPTANCE` 8/8.

## 2.78.0 — CDC Gap Closure

- Plans produit Starter/Pro/Entreprise avec affectation organisation, entitlements et quotas exécutoires.
- Ledger de consommation quotidienne pour jobs et tours Assistant.
- KMS cloud natif AWS/GCP/Azure avec chiffrement par enveloppe AES-256-GCM.
- Estimation causale observationnelle ATE/IPW avec diagnostics et garde-fou anti-surinterprétation.
- Scheduler proactif persistant avec claim conditionnel côté worker.
- CDC §46, §66 et §70 passés à implemented.
- Gate `CDC_GAP_CLOSURE_ACCEPTANCE 8/8`; CDC à 97,3 % sans falsifier les preuves externes.

## 2.77.0 — Performance & SLO Evidence

- Ajout d'une policy de budgets performance/SLO versionnée.
- Benchmark local de non-régression séparé explicitement des preuves production.
- Runner de charge HTTP externe avec concurrence, durée/volume minimums et métriques p50/p95/p99.
- Validation d'intégrité SHA-256, cible HTTPS non locale et budgets gouvernés à l'import.
- Ledger de preuves par workspace et API Operational Intelligence dédiée.
- Cockpit performance enrichi et gate `PERFORMANCE_SLO_ACCEPTANCE 8/8`.
- CDC §59 passé à implemented sans inventer de résultat production non mesuré.

## 2.76.0 — Workspace Environments & Reproducibility

- Nouveau ledger d'environnements Python/R au niveau workspace avec policy de sécurité persistée.
- Manifests canoniques SHA-256, locks de versions et vérification de dérive du sandbox.
- Héritage workspace → notebook avec overlay déterministe et empreinte effective.
- Invalidation automatique des kernels suivis lors des changements d'environnement.
- Provenance des runs Python/R enrichie avec empreinte workspace, empreinte notebook et locks.
- API de lecture/mise à jour/synchronisation/vérification de l'environnement workspace.
- Notebook Studio expose séparément manifest workspace et overlay notebook.
- Gate `WORKSPACE_ENVIRONMENT_ACCEPTANCE 8/8` ; CDC §40 et §41 passés à implemented.

## 2.75.0 — Cloud Connectors & CDC ingestion

- Ajout de connecteurs natifs S3/S3-compatible, Google Cloud Storage et Azure Blob Storage.
- Découverte d'objets cloud et matérialisation de CSV, JSON/JSONL, Parquet et XLSX.
- Nouveau mode `cdc` avec enveloppes Debezium/canoniques, primary keys, ledger d'événements et checkpoints par partition.
- Déduplication, stale-offset detection, replay idempotent, dry-run et schema drift.
- Matérialisation CDC dans des versions de dataset immuables avec lineage et refresh history.
- UI Sources & Refresh enrichie et gate `CLOUD_CDC_ACCEPTANCE` 8/8.

## v2.74.0 — Internationalisation & accessibilité

- Framework i18n natif avec catalogues français, anglais, espagnol et arabe.
- Direction RTL dynamique pour l’arabe et persistance des préférences de langue.
- Réglages contraste renforcé et réduction des animations synchronisés au profil Entreprise.
- Skip-link, focus management, navigation nommée, annonces ARIA et états sémantiques.
- Contrat Playwright accessibilité + gate `I18N_ACCESSIBILITY_ACCEPTANCE 8/8`.
- CDC §64 et §65 fermés au niveau produit ; certification externe explicitement hors périmètre.

## v2.73.0 — Model Gateway multi-provider natif

- Ajout d'un adaptateur Anthropic natif basé sur Messages API.
- Ajout d'un adaptateur Gemini natif basé sur `models.generateContent`.
- Sorties structurées JSON Schema natives pour les deux providers.
- Extension du Centre de contrôle IA et des profils provider.
- Conservation du Secret Vault, du privacy routing, des budgets et de la télémétrie.
- Nouveau gate `MODEL_GATEWAY_ACCEPTANCE` et CDC §48 passé à implemented.

## v2.72.0 — Data Storytelling avancé

- Trames analytiques multi-page déterministes, adaptées à l’audience, l’objectif et le ton.
- Claims reliés à un registre de preuves avec couverture mesurée et validation stricte.
- Prévisualisation de storytelling avant génération du rapport.
- Rendu narratif dans les exports Markdown, HTML, DOCX et PDF.
- Publication gouvernée avec reçu immuable, empreinte du contenu et Data Reliability Gate.
- UI Report Builder et Assistant raccordés au même contrat de storytelling.
- Gate `STORYTELLING_ACCEPTANCE 8/8`.

## v2.71.0 — AI Data Quality & remédiation guidée

- Plan de remédiation qualité déterministe et non mutatif.
- Prévisualisation avant/après des corrections sélectionnées.
- Déduplication et imputation prudente présélectionnables ; changements de schéma/outliers soumis à revue explicite.
- Application en une nouvelle version immuable avec audit détaillé et protection contre les plans obsolètes.
- UI Qualité et Assistant raccordés au même moteur.
- Gate `QUALITY_REMEDIATION_ACCEPTANCE 8/8`.

## v2.70.0 — AutoML Forecasting + Anomaly unifié

- Forecasting AutoML sélectionné exclusivement sur backtests rolling-origin.
- Détection d’anomalies AutoML classée par stabilité, accord inter-méthodes et plausibilité du taux.
- Expériences et Model Cards persistées pour les tâches spécialisées.
- Workflow UI/Assistant unifié avec classification, régression et clustering.
- Gate `AUTOML_UNIFIED_ACCEPTANCE 8/8`.

## v2.69.0 — Visual Analytics & NL→Viz avancé

- recommandations classées par score/confiance et justification ;
- violin, bubble, treemap, Sankey, carte de points, PCA et projection de clusters ;
- édition conversationnelle d'un graphique existant ;
- composition automatique multi-vues ;
- gate `VISUAL_ANALYTICS_ACCEPTANCE 8/8` et tests dédiés.

## v2.68.0 — Connecteurs, Data Catalog & Lineage

- Import ZIP natif multi-fichiers avec limites anti ZIP-bomb, filtrage des formats et scan antivirus des membres.
- Retries/backoff exponentiels configurables sur test, discovery et lecture des connecteurs.
- Data Catalog unifié avec recherche, domaine métier, owner, steward, tags, glossaire et statut de certification.
- Lineage cross-system : connecteur → objet externe → source → dataset → analyses/modèles/dashboards/rapports.
- UI de discovery et documentation métier intégrée à Fiabilité & Lineage.
- Migration `2.68.0-001` et gate `CATALOG_LINEAGE_ACCEPTANCE 8/8`.

## v2.67.0 — Notebook Runtime persistant Python/R

- Kernels Python/R persistants isolés avec namespace/workspace conservé entre cellules.
- Session déterministe par notebook/langage, TTL et redémarrage explicite.
- Reconstruction optionnelle de l’état par réexécution ordonnée du notebook.
- Environnements projet déclaratifs et lock des packages présents dans l’image sandbox.
- UI runtime persistante avec variables, compteur d’exécutions et reset kernels.
- Gate `NOTEBOOK_RUNTIME_ACCEPTANCE 8/8`.

## v2.66.0 — Production Acceptance & E2E

- Gate P0 `PRODUCTION_ACCEPTANCE 8/8`.
- Playwright production suite and release-candidate E2E.
- HTTP load smoke with p95/error-rate thresholds.
- Helm lint + render + Conftest in CI/release.
- Production evidence registry and sign-off verifier.
- Windows Docker Desktop production acceptance runner.
- CI/security evidence artifacts; UAT remains an explicit human sign-off.

## v2.65.0

- posture réglementaire consolidée par workspace et historique de snapshots SHA-256 ;
- catalogue de contrôles avec mappings de familles de référentiels, sans revendication de certification ;
- exceptions gouvernées et temporaires avec contrôles compensatoires ;
- remédiation assistée `proposal_only` ;
- evidence packs ZIP exportables et téléchargeables ;
- UI de conformité réglementaire intégrée à Gouvernance & sécurité ;
- gate `REGULATORY_COMPLIANCE_ACCEPTANCE`.

# Changelog

## v2.63.0 — Sécurité opérationnelle & supply chain

- SBOM backend/frontend/source avec index de digests.
- Provenance in-toto/SLSA de l’archive source reproductible.
- Signatures keyless Sigstore/Cosign des artefacts et images GHCR.
- Policy-as-code Rego exécutée sur les manifests Helm rendus.
- Rotation automatique limitée aux secrets explicitement générés.
- Rollback de release en deux phases avec confirmation et drill non destructif.
- Gate `SUPPLY_CHAIN_ACCEPTANCE 8/8`.


## v2.62.0 — Observabilité distribuée & opérations multi-cluster

- Corrélation W3C `traceparent` et consultation des traces par workspace.
- Pipeline OpenTelemetry traces avec export OTLP HTTP optionnel.
- AlertmanagerConfig multi-canaux Slack / webhook / email avec secrets externes.
- Réplications cross-region vérifiées par SHA-256 distant et audit de vérification.
- Control plane multi-cluster et bascule à confirmation en deux phases.
- Runbooks CLI exécutables pour topologie, réplications, DR et failover.
- Gate `DISTRIBUTED_OPS_ACCEPTANCE 8/8`.

## v2.61.0 — SRE automatisé & continuité multi-zone

- Recording/alert rules Prometheus et dashboard Grafana packagés dans Helm.
- Routage SRE par workspace, seuil de sévérité et code d’alerte.
- Réplication multi-cible S3 avec journal d’audit par cible.
- Exercices DR orchestrés avec restore drill et fault model non destructif.
- Métriques dérivées pour disponibilité API, succès des jobs et profondeur de file.

## v2.60.1 — Correctif build frontend

- Corrige le build Next.js strict TypeScript du Governance Control Plane : la matrice de rôles ne déréférence plus `controlPlane` lorsqu’il est nul.
- Normalise les alignements flex CSS `start/end` vers `flex-start/flex-end` pour supprimer les avertissements Autoprefixer observés au build Docker.
- Ajoute `incremental: true` au `tsconfig.json` afin que Next.js ne le modifie plus pendant le build.
- Aucun changement de schéma de données : la migration `2.60.0-001` reste la migration courante.


## v2.60.0 — Exploitation avancée & SRE
- Error budgets, alertes SLO et snapshots SRE.
- Alertes SRE intégrables aux Governed Actions.
- Backup S3-compatible signé SigV4 et manifest v2 avec checksum par fichier.
- Restore drill hebdomadaire non destructif.
- Autoscaling worker KEDA Redis optionnel.
- Chaos contrôlé désactivé par défaut et jobs `sre_probe` bornés.
- Cockpit SRE intégré à Operational Intelligence.
- Gate `SRE_ACCEPTANCE 8/8`.

## v2.59.0 — Résilience & exploitation HA
- Probes avancées et readiness sensible aux migrations.
- HPA, PDB, rolling update et topology spread Helm.
- Migrations versionnées avec Job Helm explicite.
- Sauvegarde/restauration manifestée et SHA-256, CronJob planifié.
- Rotation Vault Transit auditée et runbook de reprise après sinistre.

## 2.58.0 — Hardening de production Entreprise
- KMS externe via Vault Transit, compatible HSM selon le backend Vault déployé.
- SCIM Groups avec membres et mapping de rôles.
- Politiques organisationnelles de session et appareils approuvés.
- OpenTelemetry Collector + endpoint interne de métriques protégé.
- Chart Helm/Kubernetes optionnel, sandbox durci et Docker Compose conservé.
- Gate `HARDENING_ACCEPTANCE 8/8`.

## 2.57.0 — Fenêtre d’assistant dynamique
- Redimensionnement manuel bidimensionnel de la fenêtre flottante.
- Presets compacte / normale / agrandie.
- Persistance locale de la taille sélectionnée.
- Bornage automatique selon le viewport et adaptation responsive du contenu.
- Poignée tactile/souris et respect de `prefers-reduced-motion`.
- Gate `ASSISTANT_WINDOW_ACCEPTANCE 6/6` intégré à CI/release/préflight.

## 2.56.0 — Plateforme Entreprise
- Terminologie visible normalisée sur « Entreprise ».
- SCIM 2.0 : jetons hashés, provisioning, mise à jour des rôles et désactivation.
- Découverte OIDC par domaine email.
- Private AI strict réutilisant le moteur de politiques IA existant.
- Posture on-prem et politique d’egress explicite.
- Export Prometheus authentifié et isolé par workspace.
- Cockpit de posture Entreprise et gate `ENTREPRISE_ACCEPTANCE 8/8`.

## 2.55.0 — Governance & Control Plane
- Control Plane consolidé et matrice d’accès effective par rôle.
- Publication readiness Trust/Reliability/Certification.
- Snapshots de gouvernance SHA-256 persistants et auditables.

## 2.54.0 — Collaboration temps réel et partage gouverné

- équipes workspace persistantes ;
- WebSocket collaboration avec ticket à usage unique ;
- diff de snapshots de revues ;
- journal de décisions append-only ;
- partage ciblé et révocable sans élévation de droits ;
- événements collaboration raccordés à Governed Actions ;
- gate `COLLABORATION_ACCEPTANCE 8/8`.

## v2.53.3 — Lisibilité globale / Typography hotfix
- Échelle typographique normalisée sur toutes les feuilles CSS de la plateforme.
- Aucun `font-size` explicite avec base inférieure à 12 px.
- Modes Normal/Confort/Grand texte : facteurs 1.00 / 1.10 / 1.22.
- Hauteurs de ligne et densité des tableaux/contrôles ajustées.
- Gate `TYPOGRAPHY_ACCEPTANCE 8/8` ajouté à CI, release et préflight.

## v2.53.2 — Trust Center hotfix
- Corrige le crash `slice is not a function` à l'ouverture du Trust Center.
- Aligne le frontend sur le contrat `/datasets/{id}/versions` (`{ current_id, root_id, versions: [...] }`).
- Ajoute des garde-fous runtime pour `checks`, `warnings`, `policy` et le lineage.
- Ajoute un test de non-régression frontend dédié au Trust Center.

# v2.51.0

- ML Safety pré-entraînement et endpoint `/models/safety-audit`.
- Leakage direct bloquant, proxies/corrélations dangereuses détectés.
- IDs/quasi-identifiants/constantes exclus automatiquement.
- Gouvernance de métrique sur classes déséquilibrées.
- Split temporel réel + TimeSeriesSplit et timestamp brut exclu des features.
- Empreintes des partitions et preuve d'isolation du test final.
- Détection du surapprentissage train/validation.
- Studio ML et ML Agent alignés sur les mêmes garde-fous.

# v2.50.0
- AutoML unifié pour classification, régression et clustering.
- Leaderboard normalisé avec sens de métrique explicite (maximize/minimize).
- Historique persistant des expériences (`experiment_id`) par dataset/version.
- Clustering AutoML : K-Means, MiniBatch K-Means, BIRCH, Silhouette, Calinski-Harabasz, Davies-Bouldin.
- Garde-fous de fuite cible et isolation stricte du test final supervisé.
- ML Agent et planner alignés sur le même moteur AutoML réel.
- Studio AutoML enrichi + sidebar dynamique compacte/hover.
- Gate `AUTOML_ACCEPTANCE 8/8` intégré à CI/release/préflight.

# v2.49.0
- Report Builder composable par blocs professionnels.
- Provenance de chaque bloc et hash SHA-256 du rapport.
- Endpoint de validation d’intégrité des rapports.
- Exports PDF/DOCX/HTML/Markdown enrichis pour les nouveaux blocs.
- Gate REPORT_ACCEPTANCE 8/8 intégré à CI/release/préflight.

## 2.48.0 — Insight Engine vérifiable

- Nouveau moteur déterministe multi-signal : qualité, anomalies, tendances, segments, corrélations et changements de version.
- Ranking explicite par sévérité, confiance, impact et score 0–100.
- Fingerprints stables, déduplication et historique des scans.
- Preuve/provenance structurée pour chaque insight ; aucun calcul numérique par LLM.
- Vue Insights dédiée, feed de l'accueil et outil `generate_dataset_insights` du Statistics Agent.
- Gate `INSIGHT_ACCEPTANCE 8/8` intégré à CI, release et préflight.

## 2.47.0 — NLQ gouverné & Semantic Layer métier

- Définitions métier, unités, synonymes et permissions par rôle sur les objets sémantiques.
- Glossaire métier lié à des métriques/dimensions et utilisé par le résolveur NLQ.
- Traçabilité des tables et relations réellement utilisées.
- Refus explicite des tentatives de contournement d'un objet sémantique restreint via NLQ/SQL.
- Validation read-only et provenance de la résolution Text-to-SQL / Semantic Query.
- Gate `SEMANTIC_ACCEPTANCE 8/8` intégré à CI, release et préflight.

## 2.46.0 — AI Orchestrator multi-agent réel

- Six rôles runtime : Data, Statistics, ML, Visualization, Report et Critic.
- Routage déterministe tool → spécialiste avec overrides contrôlés.
- Prévalidation de délégation avant tout tool-call.
- Validation spécialiste des résultats et arrêt sur sortie vide/invalide.
- Critic Agent vérifiant exécution et cohérence du routage.
- Trace `agent_trace` et endpoint `/api/v1/ai/assistant/agents`.
- Gate `MULTI_AGENT_ACCEPTANCE` 8/8 intégré à CI/release/preflight.

# Changelog

## 2.45.0 — Assistant multimodal et proactif

- Monitoring déterministe et détection de workflow bloqué.
- Alertes fingerprintées avec cooldown anti-spam.
- Snooze/masquage et modes vocaux persistants.
- Fichiers générés par les outils téléchargeables depuis la conversation.
- Nouveau gate `ASSISTANT_MULTIMODAL_ACCEPTANCE 8/8`.

## 2.44.0 — Assistant V1 tool-connected
- Catalogue du planner limité aux outils réellement exécutables dans le runtime courant.
- Outils déclarés mais non bridgés refusés avant planification/exécution et masqués du catalogue utilisateur.
- Contexte live relu depuis l'Event Bus au moment exact des messages, confirmations et refus.
- Resynchronisation automatique de l'UI après transformation de dataset, création de modèle, rapport, visualisation ou cellule notebook.
- Diagnostic assistant enrichi avec nombre d'outils exécutables/déclarés et liste des capacités indisponibles.
- Nouveau gate `ASSISTANT_ACCEPTANCE` 8/8 intégré à la CI et au préflight.
- Ajout des tests backend/frontend de non-régression v2.44.

## 2.43.0 — Data Workspace reproductible
- Notebooks liés explicitement à une version immuable du dataset et visibles sur toute sa lignée.
- Rebinding d'un notebook vers une version précise sans réécriture de l'historique des runs.
- Exécution ordonnée « Tout exécuter » avec arrêt contrôlé sur erreur.
- Provenance enrichie de chaque run : root/version/lignée/dimensions/fingerprint SHA-256 + hash du code.
- Artefacts Python/R persistés, téléchargeables et promouvables en nouvelle version gouvernée CSV/JSON.
- SQL local maintenu strictement read-only ; Python/R restent confinés dans le sandbox interne.
- Nouveau gate `WORKSPACE_ACCEPTANCE` 8/8 intégré à la CI et au préflight.
- Ajout des tests backend et frontend de non-régression v2.43.

## 2.42.0 — Data Preparation Completion
- Pipelines multi-datasets désormais enregistrables et rejouables avec dépendances explicites.
- Ajout des bindings de remplacement pour datasets secondaires au replay.
- Prévalidation complète en mémoire avant persistance afin d'éviter les branches partielles.
- Jointures multi-clés exposées dans le Studio de préparation.
- GroupBy multi-agrégations exposé dans l'UI.
- Nouveau feature engineering : binning numérique, lag et rolling features.
- Nouveau gate `PREPARATION_ACCEPTANCE` 8/8 intégré à la CI et au préflight.
- Ajout de tests backend et frontend de non-régression v2.42.

## 2.41.0 — Executable MVP Acceptance
- Remplacement du gate MVP purement structurel par une matrice exécutable de 16 exigences.
- Ajout du workflow intégré import → profiling → quality → preparation → statistics → visualization → history → export.
- Ajout d’un E2E déployé via le proxy frontend `/api/backend`.
- Correction P0 de l’import JSON : séparation données `<id>.json` / métadonnées `<id>.meta.json`.
- Compatibilité maintenue avec les sidecars legacy valides.
- CI renforcée avec `scripts/mvp_acceptance.py --check`.

## 2.40.4 — Feature Store strict typing
- Correction du build Next.js dans `FeatureServingView.tsx` : `columnNames.map(name => ...)` n’utilise plus un paramètre implicitement `any`.
- Normalisation explicite de `columns` en `AnyObj[]` et de `columnNames` en `string[]`.
- Typage explicite `name: string` sur les trois callbacks du sélecteur de features.
- Ajout d’un test de non-régression dédié.

## 2.40.3 — Frontend null-safety consolidation
- Correction du build Next.js dans Sources & Refresh : `connectorSpec.options` n’est plus accédé directement depuis un JSX où `connectorSpec` peut être nul.
- Capture stable de `connectorOptions` avant le rendu.
- Capture null-safe de `signoff_required` dans ComplianceCenter.
- Capture stable `activeModel` dans les callbacks async de ResponsibleAIView.
- Ajout de tests de non-régression couvrant ces trois zones.

## 2.40.2 — Frontend XAI counterfactual payload typing
- Correction du build Next.js : le payload de `runModelCounterfactuals()` possède désormais le type exact attendu par l’API.
- `row` est explicitement traité comme `Record<string, unknown>`.
- Le modèle XAI non nul reste capturé via `activeModel`.
- Ajout d’un test de non-régression dédié au contrat de payload contre-factuel.

## 2.40.1 — Frontend XAI nullable-model hotfix
- Correction du build Next.js : les callbacks XAI capturent une référence `activeModel` non nulle après la garde de rendu.
- Ajout d’un test de non-régression empêchant le retour de `model.task` non sécurisé.


## 2.39.0 — Repository Cleanup & Professional Structure
- Racine du dépôt réduite aux fichiers opérationnels.
- 35 manifests historiques déplacés dans `docs/history/manifests/`.
- Guide de migration historique déplacé dans `docs/history/migrations/`.
- Nouvelle documentation `docs/development/PROJECT_STRUCTURE.md`.
- Ajout de `.gitignore` et `.editorconfig`.
- Nouveau contrôle `scripts/repository_hygiene.py --check`.
- Contrôle d'hygiène intégré au préflight Windows et à la CI.
- Aucun changement des moteurs analytiques ni des API métier.

## 2.12.0 — Identity, SSO & Secret Management
- Sessions Entreprise persistantes avec identifiant serveur et révocation immédiate.
- Access tokens courts et refresh tokens rotatifs ; seul le hash du refresh token est stocké.
- Endpoints de liste/révocation de sessions et fermeture globale.
- SSO OIDC Authorization Code + PKCE S256.
- State à usage unique, nonce et discovery OIDC.
- Validation cryptographique RS256 via JWKS avec contrôle issuer/audience/expiration/nonce.
- Provisioning JIT et mapping d'identités externes.
- Restriction facultative des domaines email et rôle JIT par défaut.
- Secret Vault versionné avec backends local chiffré, variable d'environnement et HashiCorp Vault KV v2.
- Rotation de secret avec historique de versions et retrait de la version précédente.
- Nouvelle interface **Gouverner → Identité & Secrets**.
- API frontend avec refresh automatique après 401.
- Garde SSRF/HTTPS pour appels externes OIDC et Vault.
- 64 tests backend validés.

## 2.11.0 — Entreprise Action Connectors
- Connecteurs natifs Slack, Microsoft Teams, Jira et Email SMTP.
- Slack Incoming Webhook et Slack Web API `chat.postMessage`.
- Jira Cloud issue creation via REST v3.
- SMTP/STARTTLS/SSL avec login ou OAuth2 client credentials.
- Credentials et endpoints webhook sensibles chiffrés au repos.
- Masquage des headers sensibles et des endpoints dans les réponses API.
- OAuth2 `client_credentials` côté serveur ; Authorization Code reste planifié.
- Nouveau `approval_mode=chain` avec jusqu'à 6 étapes ordonnées par rôle/utilisateur.
- Progression d'approbation persistante et séparation stricte des rôles.
- Endpoint de test explicite des destinations pour Owner/Admin.
- UI Actions Center refondue avec type de connecteur, auth et stepper d'approbation.
- 59 tests backend validés.

## v2.9.0

- Operational Intelligence Center ;
- télémétrie HTTP best-effort par workspace ;
- disponibilité API et latences p50/p95/p99 ;
- job/refresh success rates et SLO internes ;
- classement des fonctionnalités réellement utilisées ;
- stockage tokens/coûts provider-aware sans estimation fictive ;
- AI Analyst Evaluation Lab ;
- suites, cas, runs et résultats d’évaluation persistés ;
- checks intent / Critic / tools / contenu / findings / durée / valeur tolérée ;
- retry/backoff exponentiel via Redis sorted set ;
- historique séparé des tentatives de jobs ;
- nouvelle vue Gouverner → Observabilité & Eval ;
- 52 tests backend passent.

# v2.8.0 — Data Reliability & Lineage

- Data Contracts persistants par lignée de dataset ;
- règles required columns, volume, nullité, unicité, plage, domaine, dtype, regex ;
- distribution drift numérique par KS et catégoriel par TVD ;
- score de fiabilité pondéré par sévérité ;
- modes monitor / warn / block ;
- contrôles automatiques sur versions dérivées et refresh connecteurs ;
- événements de fiabilité persistants ;
- Publication Gate fail-closed sur la version exacte ;
- certification Review Center bloquée si un contrat critique en mode block échoue ;
- export de rapports Entreprise bloqué par le même gate ;
- lineage source → dataset → analyse / modèle / métrique / dashboard / rapport ;
- impact analysis downstream ;
- nouveau Reliability Center professionnel ;
- 50 tests backend passent.

# v2.7.0 — Sources & Refresh

- PostgreSQL et MySQL comme sources SQL réelles ;
- credentials chiffrés au repos via Fernet / AUTH_SECRET ;
- test de connexion et découverte schémas/tables/colonnes ;
- sources table ou requête read-only ;
- full refresh et incremental refresh avec watermark ;
- matérialisation en versions de dataset immuables ;
- freshness SLA avec états fresh/warning/stale/error ;
- schema drift avec politiques warn/fail ;
- scheduler worker + claim atomique des échéances ;
- job asynchrone `connector_refresh` tenant-aware ;
- observabilité des refresh et historique détaillé ;
- écran professionnel `Sources & Refresh` ;
- 45 tests backend.

# Changelog

## v2.6.0 — Collaboration & Review

- Review Center professionnel ;
- workflow Draft → In review → Approved / Changes requested ;
- ownership et reviewer assigné ;
- commentaires persistants et résolus ;
- mentions et notifications ;
- historique append-only des décisions ;
- certifications gouvernées avec expiration/révocation ;
- RBAC collaboration ;
- 41 tests backend.

## v2.5.0

- Inbox analytique proactive dans l'espace Décider ;
- surveillances persistantes sur métriques sémantiques ;
- configuration automatique à partir des métriques certifiées ;
- seuils de variation, anomalie robuste médiane/MAD et détection de rupture ;
- priorités medium/high/critical ;
- déduplication des alertes par fingerprint ;
- workflow open / acknowledged / resolved / dismissed ;
- tendance et preuve déterministes dans chaque alerte ;
- recommandations d'investigation par dimensions sémantiques ;
- endpoints de watches, scans, summary et Inbox ;
- type de job Redis `proactive_scan` ;
- nouvelle interface professionnelle Proactive Intelligence ;
- 37 tests backend passent.

## v2.4.0

- NLQ semantic-first avec exécution multi-table ;
- planificateur sémantique déterministe FR/EN ;
- agrégation explicite temporaire sans modifier la métrique gouvernée ;
- AI Analyst raccordé au Semantic Query Engine ;
- Tool Registry enrichi avec `semantic_query` ;
- widgets `semantic_kpi` et `semantic_chart` ;
- filtres dashboard sur dimensions liées ;
- cross-filter multi-table ;
- drill-down hiérarchique ;
- jointures multi-hop dans les schémas en flocon ;
- projection sécurisée vers la table de faits pour synchroniser widgets physiques et sémantiques ;
- 35 tests backend passent.

## v2.3.0

- Semantic Model Studio v2 multi-tables.
- Relations N:1 / 1:1 validées avec protection anti fan-out.
- Métriques calculées via AST sûr, sans eval/exec.
- Dimensions certifiées et hiérarchies métier.
- Semantic Query Engine multi-table.
- Time intelligence : previous period, YoY, running total, YTD, rolling mean/sum.
- Catalogue de tables tenant-aware.
- Validateur de modèle sémantique et score de santé.
- Trust Center enrichi par la validation sémantique.
- Interface Semantic Studio réorganisée en cinq onglets.
- 31 tests backend.

# v2.2.0

- middleware tenant-aware pour toutes les routes dataset ;
- propagation automatique token/workspace depuis le frontend ;
- RBAC global sur lectures, analyses, modèles, transformations et publication ;
- RLS et sécurité colonne appliquées dans `storage.load_dataframe` ;
- isolation du catalogue par workspace ;
- accès refusé aux datasets non liés ;
- héritage des policies sur la lignée des versions ;
- liaison automatique des versions dérivées au workspace actif ;
- correction RLS-before-CLS et comportement fail-closed ;
- snapshot des policies matérialisées pour les versions dérivées ;
- worker Redis tenant-aware ;
- endpoint `/datasets/{id}/access-context` ;
- badge UI `Accès gouverné` ;
- 28 tests backend.

# v2.1.0

- Identité locale avec bootstrap, login, scrypt et bearer token signé.
- Organisations et workspaces multi-utilisateurs.
- RBAC owner/admin/data_scientist/analyst/viewer.
- PostgreSQL comme metadata store Entreprise, fallback SQLite local.
- Provisionnement de membres.
- Liaison dataset ↔ workspace.
- Registre de politiques colonnes/lignes et governed preview exécuté réellement.
- Journal d'audit consolidé.
- File de jobs Redis + worker séparé + suivi/annulation.
- Nouvelle zone UI **Gouverner**.
- 25 tests backend passants.

# v2.0.0 — Semantic Intelligence & Professional Shell

- benchmark marché 2026 documenté ;
- navigation réorganisée en six espaces orientés workflow ;
- Command Palette globale ;
- Goal Playbooks sur l'accueil ;
- Semantic Studio : métriques, dimensions, synonymes, unités, certification ;
- Metric Pulse déterministe ;
- NLQ ancré sur la couche sémantique ;
- AI Analyst ancré sur synonymes/métriques avec provenance sémantique ;
- Trust Center ;
- Decision Lab : what-if et sensibilité du modèle sauvegardé ;
- topbar de contexte dataset/version/qualité/confiance ;
- styles visuels simplifiés et progressive disclosure ;
- 23 tests backend.

# v1.3.0

- Dashboard Builder persistant ;
- widgets KPI, graphiques et texte ;
- grille responsive avec tailles de widgets et réordonnancement drag-and-drop ;
- filtres globaux déterministes ;
- cross-filtering depuis les graphiques en barres ;
- persistance locale des définitions ;
- endpoints CRUD + preview ;
- calculs KPI/graphiques côté backend après filtrage ;
- 20 tests backend passent.

# v1.2.0 — Report Intelligence

- narration analytique automatique fondée sur les résultats calculés ;
- constats prioritaires avec preuve et interprétation ;
- sélection et génération automatiques de figures pertinentes dans les rapports ;
- légendes enrichies avec objectif et lecture analytique ;
- section automatique des limites et précautions d’interprétation ;
- verrouillage des visualisations automatiques sur la version du dataset ;
- détection des identifiants affinée afin de ne plus masquer les mesures numériques continues uniques ;
- Report Studio enrichi de contrôles pour narration automatique, figures automatiques et nombre maximal de figures ;
- export PDF/DOCX/HTML/Markdown adapté aux nouvelles sections ;
- 19 tests backend passent ;
- QA visuelle PDF et DOCX effectuée sur 13 pages de chaque export.

# v1.1.1

- refonte complète du Report Builder en **Professional Report Studio** ;
- modèles Exécutif / Analytique / Technique ;
- page de garde et sommaire automatiques ;
- synthèse exécutive avec KPI, constats et recommandations ;
- organisation explicite et numérotée des sections ;
- sélection individuelle des visualisations à publier ;
- aperçu document dans l'interface ;
- PDF professionnel avec en-têtes, pieds de page, pagination et graphiques vectoriels ;
- DOCX professionnel avec styles, pagination et graphiques intégrés ;
- HTML print-ready avec graphiques SVG et sommaire cliquable ;
- support de rendu des graphiques bar, line, area, histogram, density, scatter, heatmap et box ;
- métadonnées auteur/organisation/sous-titre ;
- 18 tests backend passent ;
- QA visuelle PDF et DOCX effectuée par rendu de toutes les pages d'un rapport de test.

# Changelog

## v1.1.0

- Analytical Overview sur l’accueil.
- Insights déterministes et recommandations analytiques.
- Visualisations épinglables depuis Visualization Studio.
- Registre local des visualisations par dataset/version.
- Section de rapport pour les visualisations épinglées.
- API dashboard et saved visualizations.

v1.0.2

- navigation latérale regroupée : Explorer / Analyser / Modéliser / Partager ;
- interface des tests statistiques simplifiée et plus responsive ;
- détection des identifiants probables et exclusion des sélections analytiques automatiques ;
- tailles d’effet : Cohen d, rank-biserial, eta², epsilon², r/rho, V de Cramér, odds ratio et Cohen dz selon le test ;
- visualisations adaptées aux tests : boxplots, scatterplots et heatmap de contingence ;
- régression enrichie : forest plot coefficients + IC 95 %, Q-Q plot, histogramme des résidus et distance de Cook ;
- ANOVA enrichie : eta² / eta² partiel et intervalles de confiance Tukey ;
- forecasting : benchmark graphique RMSE + MAE ;
- XAI régression : résidus vs prédictions et observé vs prédit ;
- tableaux techniques rendus repliables lorsque pertinent ;
- 16 tests backend passent.

# v1.0.1

- interface visuellement épurée ;
- correction des risques de superposition dans les formulaires et panneaux ;
- responsive amélioré ;
- dashboard dataset enrichi ;
- graphiques qualité ajoutés ;
- heatmap de corrélation ;
- densité KDE, heatmap et area chart dans Visualization Studio ;
- tri temporel amélioré des courbes ;
- scree plot ACP enrichi avec variance cumulée ;
- heatmap de covariance ACP ;
- graphiques clustering : taille, silhouette, inertie ;
- benchmark graphique AutoML ;
- graphique de scores d'anomalie ;
- labels et boxplots rendus anti-chevauchement ;
- 14 tests backend.

# v0.9.2

- Correction du build Next.js en mode TypeScript strict dans `XaiView`.
- Les appels asynchrones `getModelDiagnostics` et `explainModelPrediction` utilisent explicitement un modèle non nul après la garde UI.
- Ports maintenus à 3005 (web) et 8005 (API).

# Changelog

## v0.9.1

- correction du build Next.js : `result is possibly null` dans les handlers asynchrones ;
- correction préventive des mêmes accès nullable dans Préparation, Régression, ANOVA, ACP, Clustering, tests, visualisation, SQL, forecasting, anomalies et AI Analyst ;
- remplacement CSS `align-items: end` par `align-items: flex-end` pour supprimer le warning Autoprefixer ;
- ports inchangés : frontend 3005, API 8005 ;
- 12 tests backend passent.

## v0.9.0

- AI Analyst réellement exécutable ;
- routeur déterministe de demandes analytiques FR/EN ;
- Tool Registry ;
- plan analytique et journal d'exécution ;
- orchestration de profiling, qualité, corrélations, régression, ANOVA, clustering, AutoML, forecasting, anomalies et decision support ;
- Critic avec contrôles de provenance ;
- constats reliés aux moteurs calculés ;
- endpoint `/ai/capabilities` ;
- endpoint `/ai/analyze` ;
- nouvel écran AI Analyst ;
- ports Docker déplacés vers 3005 / 8005 ;
- 12 scénarios de tests backend passent.

## v0.8.0

- module Forecasting avec split temporel de validation ;
- benchmark naïf, naïf saisonnier, tendance linéaire et lissage exponentiel ;
- intervalles empiriques de prévision à 95 % ;
- détection d'anomalies IQR, z-score robuste et Isolation Forest ;
- diagnostics XAI sur holdout final lorsque disponible ;
- matrice de confusion, ROC/PR, calibration binaire et Brier score ;
- diagnostics de résidus en régression ;
- explications locales par perturbation vers baseline ;
- baselines et indices du test final persistés dans les artefacts modèles ;
- nouveaux écrans Forecasting, Anomalies et Explicabilité XAI ;
- 10 scénarios de tests backend passent.

## v0.7.0

- AutoML initial réel ;
- split 60/20/20 train/validation/test ;
- cross-validation ;
- benchmark multi-modèles ;
- tuning contrôlé sans utilisation du test final ;
- détection class imbalance, identifiants, temporalité et leakage heuristique ;
- permutation feature importance ;
- Model Cards ;
- registre local de modèles ;
- nouveaux endpoints AutoML / registry / card ;
- interface Modélisation refondue pour AutoML.

## v0.6
- Statistical Test Advisor déterministe.
- Tests : Student, Welch, Mann-Whitney, ANOVA 1 facteur, Kruskal-Wallis, Pearson, Spearman, Chi-deux, Fisher, t apparié, Wilcoxon.
- Matrices de corrélation Pearson/Spearman avec p-values et effectifs.
- SQL Workspace local en lecture seule.
- Intégration cible DuckDB + Polars, avec fallback de test hors-ligne.
- Endpoint d'observabilité du moteur de données.
- Visualization Studio : auto, histogramme, scatter, boxplot, bar et line.
- Recommandations de visualisations selon les types de variables.
- Agrégations serveur pour les graphiques.
- 8 scénarios de tests backend passent.
- Syntaxe TS/TSX validée via le transpileur TypeScript.

## v0.5
- Pipeline visuel relié au lineage réel.
- Pipelines nommés sauvegardables et rejouables.
- Catalogue local des datasets persistés.
- Jointures inner/left/right/outer entre datasets.
- Concaténation de lignes et de colonnes.
- Feature engineering via DSL arithmétique sûre, sans `eval`.
- One-hot encoding.
- GroupBy + agrégations.
- Pivot table.
- Unpivot / Melt.
- Extraction de composantes de date.
- Provenance du dataset secondaire dans les opérations de combinaison.
- 7 tests backend passent.

## v0.4
- Data Preparation Studio réel.
- 10 familles de transformations déterministes.
- Versioning immuable des datasets.
- Historique de versions et réactivation/rollback non destructif.
- Métadonnées de lineage parent/root.
- Affichage de la version active dans l'interface.
- Endpoints `/versions` et `/transform`.

## v0.3
- Régression linéaire et diagnostics.
- ANOVA un/deux facteurs, Tukey, Levene, Shapiro-Wilk.
- ACP KMO/Bartlett/contributions.
- K-means/silhouette/profils.

## v0.2
- Refonte UI inspirée de l'application historique.
- Statistiques descriptives et interface de navigation modulaire.
## v1.0.0

- Report Builder reproductible ;
- exports PDF, DOCX, HTML, Markdown ;
- persistance et consultation de l'historique AI Analyst ;
- NLQ/Text-to-SQL déterministe avec validation read-only ;
- interface Rapports activée ;
- NLQ intégré au SQL Workspace ;
- scripts PowerShell installation/start/stop Windows ;
- caches BuildKit pip/npm ;
- ports conservés à 3005/8005 ;
- 13 tests backend.
## v2.64.1

- Hotfix assistant : le panneau Contexte actif devient scrollable et ne peut plus être tronqué par la hauteur de la fenêtre.
- Affichage contextuel enrichi : workspace, rôle, navigation, qualité, sélection, modèle, gouvernance, schéma et événements récents.
- Ajout d’un snapshot technique complet, repliable, correspondant au contexte réellement transmis à l’orchestrateur.
- Projection sémantique enrichie côté backend avec maintien des garde-fous de confidentialité et exclusion des lignes brutes.
- Synchronisation des graphiques/rapports générés dans le contexte actif.

## v2.64.0

- admission Kubernetes opt-in via Kyverno `ClusterPolicy` ;
- vérification Sigstore/Cosign keyless des images configurable ;
- durcissement runtime API/Web/Worker/Sandbox/OTel : non-root, seccomp RuntimeDefault, no privilege escalation, drop ALL capabilities ;
- root filesystem en lecture seule avec volumes temporaires dédiés ;
- règles Falco livrées pour shells, écritures sensibles et package managers ;
- ingestion d'événements runtime security ;
- scans de conformité continue avec détection de dérive ;
- evidence packs JSON signés par digest SHA-256 ;
- CronJob Kubernetes de conformité continue ;
- policy-as-code Rego étendue aux contrôles runtime ;
- gate `RUNTIME_SECURITY_ACCEPTANCE` intégré à la CI et à la release.
