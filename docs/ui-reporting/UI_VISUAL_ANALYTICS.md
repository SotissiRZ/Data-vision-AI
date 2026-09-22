# DataVision AI — UI & Visual Analytics v2.69

## Objectif

Présenter d’abord les éléments qui aident réellement à interpréter une analyse, puis laisser les détails numériques accessibles sans surcharger l’écran. L’interface doit rester lisible sur un écran portable comme sur un grand écran.

## Architecture visuelle

La navigation est organisée en quatre familles :

- **Explorer** : Accueil, Données, Statistiques descriptives, Qualité, Préparation ;
- **Analyser** : Tests & corrélations, Visualization Studio, SQL, Régression, ANOVA, ACP, Clustering ;
- **Modéliser** : Modélisation, Forecasting, Anomalies, XAI, Prédictions, AI Analyst ;
- **Partager** : Rapports.

Les formulaires utilisent des grilles responsives `minmax(0, 1fr)`, les panneaux se replient en une colonne lorsque nécessaire et les visualisations larges possèdent leur propre zone de défilement.

## Sélection intelligente des variables

Les colonnes ressemblant à des identifiants (`ID`, `*_id`, quasi-uniques) sont signalées comme **identifiant probable** et ne sont plus choisies automatiquement pour :

- corrélations ;
- tests statistiques ;
- visualisations automatiques ;
- ACP ;
- clustering ;
- forecasting ;
- anomalies ;
- AutoML.

Elles restent disponibles pour une sélection manuelle lorsqu’un cas d’usage le justifie.

## Tests statistiques

Le résultat principal met en avant :

- statistique de test ;
- p-value ;
- taille d’effet lorsque disponible ;
- hypothèses/diagnostics utiles.

Visualisations contextuelles :

- Student / Welch / Mann-Whitney / ANOVA / Kruskal : distributions par groupe et boxplots ;
- Pearson / Spearman / tests appariés : nuage de points ;
- Chi² / Fisher : heatmap de contingence ;
- matrice de corrélation : heatmap avec matrice numérique repliable.

## Régression

Visualisations principales :

1. coefficients avec IC 95 % ;
2. résidus vs valeurs ajustées ;
3. Q-Q plot ;
4. histogramme des résidus ;
5. observé vs prédit ;
6. observations influentes par distance de Cook.

Les informations AIC/BIC et diagnostics détaillés restent disponibles dans une section repliable.

## ANOVA

- boxplots par groupe ;
- eta² pour un facteur ;
- eta² partiel pour deux facteurs ;
- intervalles de confiance du post-hoc Tukey ;
- tableau complet toujours disponible.

## Autres visualisations

### Dataset
- valeurs manquantes ;
- types de variables ;
- cardinalité.

### Qualité
- taux de valeurs manquantes ;
- alertes par sévérité.

### Visualization Studio
- recommandations scorées et expliquées ;
- histogramme, densité KDE, scatter, bubble ;
- boxplot et violin ;
- bar, line, area ;
- heatmap de corrélation ;
- treemap et Sankey ;
- carte de points géographiques ;
- projection PCA et clusters ;
- édition conversationnelle d'un graphique existant ;
- composition automatique multi-vues.

### ACP
- scree plot ;
- variance cumulée ;
- projection PC1/PC2 ;
- cercle des charges ;
- contributions ;
- heatmap de covariance.

### Clustering
- projection PCA 2D ;
- taille des clusters ;
- silhouette selon K ;
- inertie / méthode du coude ;
- profils et centres.

### ML / AutoML
- scores de validation ;
- scores de cross-validation ;
- importance des variables.

### Forecasting
- série historique + prévision ;
- intervalles de prévision ;
- benchmark RMSE ;
- benchmark MAE.

### Anomalies
- top des scores d’anomalie.

### XAI
- permutation importance ;
- matrice de confusion / ROC / PR / calibration pour classification ;
- résidus vs prédictions et observé vs prédit pour régression ;
- explication locale par perturbation contrôlée.

## Validation

- backend : **16 tests passent** ;
- compilation Python : OK ;
- syntaxe `page.tsx` et `api.ts` : validée avec le transpileur TypeScript ;
- build Docker/Next complet : à confirmer sur l’environnement utilisateur.
