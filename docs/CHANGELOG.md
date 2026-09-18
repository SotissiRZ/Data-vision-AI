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