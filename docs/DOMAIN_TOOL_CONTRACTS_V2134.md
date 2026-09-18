# DataVision v2.13.4 — Domain Tool Contracts

## Objectif

L'agent ne doit pas seulement connaître le nom d'un outil. Il doit connaître
le contrat exact de ses paramètres.

Exemple :

```text
run_statistical_test
├── test
├── outcome
├── group
├── variables
├── alpha
└── alternative
```

Si le LLM produit un argument invalide, l'action est bloquée avant le moteur.

## Domaines couverts

### Data
- profiling ;
- valeurs manquantes ;
- transformations versionnées ;
- fusion ;
- suppression de colonnes sur nouvelle version.

### Statistiques
- t-test ;
- Welch ;
- Mann-Whitney ;
- Wilcoxon ;
- chi-square ;
- Fisher ;
- ANOVA ;
- Kruskal-Wallis ;
- Pearson ;
- Spearman ;
- normalité ;
- homoscédasticité ;
- régressions.

### Visualisation
- bar ;
- line ;
- area ;
- scatter ;
- histogram ;
- boxplot ;
- violin ;
- heatmap ;
- matrice de corrélation ;
- density ;
- bubble ;
- treemap ;
- Sankey ;
- map ;
- time series ;
- PCA ;
- clustering.

### ML
- classification ;
- régression ;
- clustering ;
- forecasting ;
- XAI.

### GIS
Première couche de contrats :
- reprojection ;
- jointure spatiale ;
- buffer.

### Reporting / fichiers
- inspection fichier ;
- export ;
- PDF/DOCX/HTML/Markdown/PPTX ;
- connecteurs externes.

## Schémas dynamiques

`GET /ai/assistant/tools` expose maintenant le JSON Schema de chaque outil.

Le frontend peut donc construire dynamiquement :
- formulaires de confirmation ;
- éditeurs d'arguments ;
- explications utilisateur ;
- validation avant exécution.

## Workflows standards

DataVision expose aussi des templates :

```text
analyze_dataset
compare_groups
predict_target
geospatial_analysis
```

Ils ne remplacent pas le planner. Ils constituent des structures vérifiables
que l'agent peut utiliser comme points de départ.
