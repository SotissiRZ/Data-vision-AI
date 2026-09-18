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
