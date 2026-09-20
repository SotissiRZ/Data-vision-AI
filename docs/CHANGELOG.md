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
- Nouvelle documentation `docs/PROJECT_STRUCTURE.md`.
- Ajout de `.gitignore` et `.editorconfig`.
- Nouveau contrôle `scripts/repository_hygiene.py --check`.
- Contrôle d'hygiène intégré au préflight Windows et à la CI.
- Aucun changement des moteurs analytiques ni des API métier.

## 2.12.0 — Identity, SSO & Secret Management
- Sessions Enterprise persistantes avec identifiant serveur et révocation immédiate.
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

## 2.11.0 — Enterprise Action Connectors
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
- export de rapports Enterprise bloqué par le même gate ;
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
- PostgreSQL comme metadata store Enterprise, fallback SQLite local.
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