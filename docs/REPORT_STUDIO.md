# Professional Report Studio — DataVision AI v1.2.0

## Objectif

Le Report Studio transforme les résultats analytiques de DataVision en documents réellement présentables à une direction, un client, un chercheur ou une équipe technique.

Le rapport reste reproductible : dataset, version, visualisations et session AI Analyst sont conservés dans la définition JSON du rapport.

Depuis la v1.2.0, **Report Intelligence** complète ce studio avec une narration analytique automatique, une sélection intelligente des figures et une section dédiée aux limites d’interprétation. Voir `REPORT_INTELLIGENCE.md`.

## Modèles

### Exécutif

Priorité à la synthèse, aux KPI, aux alertes, aux recommandations et aux graphiques décisionnels.

### Analytique

Équilibre entre synthèse, qualité, statistiques descriptives, visualisations et interprétation.

### Technique

Priorité aux détails méthodologiques, aux résultats numériques, aux limites et à la provenance.

## Structure

Un document peut contenir :

1. Synthèse exécutive
2. Vue d'ensemble des données
3. Qualité des données
4. Statistiques descriptives
5. Analyses visuelles
6. Analyse AI Analyst
7. Méthodologie
8. Provenance et reproductibilité

Le sommaire et la numérotation sont produits à partir des sections réellement sélectionnées.

## Visualisations

Les visualisations enregistrées depuis Visualization Studio peuvent être sélectionnées individuellement dans Report Studio.

Les exports rendent réellement les types suivants :

- bar ;
- line ;
- area ;
- histogram ;
- density ;
- scatter ;
- heatmap ;
- box.

PDF utilise les primitives vectorielles ReportLab. DOCX reçoit des images PNG générées à partir du même moteur graphique. HTML reçoit des SVG.

## PDF

Le PDF contient :

- page de garde ;
- sommaire ;
- sections numérotées ;
- en-tête et pied de page ;
- pagination ;
- cartes KPI ;
- tableaux stylés ;
- graphiques ;
- méthodologie ;
- provenance.

## DOCX

Le DOCX contient :

- couverture indépendante ;
- hiérarchie de styles Word ;
- sommaire statique ;
- tableaux avec en-têtes stylés ;
- figures intégrées ;
- en-tête et pagination à partir de la page 2.

## HTML

Le HTML est autonome et imprimable. Il inclut :

- CSS embarqué ;
- sommaire avec ancres ;
- grille KPI ;
- graphiques SVG ;
- design responsive ;
- règles `@media print`.

## API

`POST /api/v1/datasets/{dataset_id}/reports`

Exemple :

```json
{
  "title": "Performance commerciale",
  "subtitle": "Synthèse mensuelle",
  "author": "Equipe Data",
  "organization": "Mon organisation",
  "template": "analytical",
  "sections": [
    "executive_summary",
    "overview",
    "quality",
    "descriptive",
    "visualizations",
    "methodology",
    "provenance"
  ],
  "analysis_session_id": null,
  "visualization_ids": []
}
```

## Règles de fiabilité

- les chiffres proviennent des moteurs calculatoires ;
- la version du dataset est verrouillée ;
- les visualisations sont liées à la version du dataset ;
- les rapports stockent leur structure avant export ;
- les exports sont régénérables à partir du rapport sauvegardé.
