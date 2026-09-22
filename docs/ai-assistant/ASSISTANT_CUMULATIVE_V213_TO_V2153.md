# DataVision AI — intégration cumulative v2.13 → v2.15.3

Cette version n'est pas un patch isolé. Elle est issue de la fusion de la base
complète v2.12 avec toutes les étapes assistant développées ensuite.

## Chaîne cumulative

```text
v2.12 Entreprise baseline
  ↓
v2.13.0 Floating assistant + voice + semantic context
  ↓
v2.13.1 Tool Registry + Activity + Memory + Executor
  ↓
v2.13.2 Plan Validator
  ↓
v2.13.3 Host Bridge + ActionRun + Realtime
  ↓
v2.13.4 Domain Contracts
  ↓
v2.14.0 Orchestrator + Intent + Critic + Recovery
  ↓
v2.14.1 Strict sequencing + TurnRun resume
  ↓
v2.14.2 Floating UI bound to orchestrator
  ↓
v2.15.0 Provider-agnostic Model Gateway
  ↓
v2.15.3 Native v2.12 service/RBAC integration
```

## Intégration native v2.12

Les outils suivants sont reliés aux moteurs réels de la v2.12 :

- profiling ;
- valeurs manquantes ;
- transformations versionnées ;
- fusion de datasets ;
- suppression de colonnes par nouvelle version ;
- visualisations ;
- tests statistiques ;
- régression ;
- leakage checks ;
- AutoML classification/régression ;
- diagnostics XAI déjà disponibles ;
- génération/export de rapports ;
- inspection de datasets importés ;
- export CSV/XLSX/Parquet/JSON.

Les contrats GIS existent mais l'exécution SIG reste explicitement partielle,
car la v2.12 ne contient pas encore le moteur géospatial correspondant.

SHAP et PPTX restent également marqués partiels conformément à la base existante.
