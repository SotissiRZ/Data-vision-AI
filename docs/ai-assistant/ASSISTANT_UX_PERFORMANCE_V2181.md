# DataVision v2.18.1 — Assistant UX & performance conversationnelle

## 1. Synthèse vocale

Nouvelle préférence :

```text
Synthèse vocale [ ]
```

Valeur par défaut : OFF.

Stockage navigateur :

```text
datavision.assistant.tts.enabled
```

Le microphone reste indépendant.

## 2. Dataset assessment

Nouvelle intention :

```text
dataset_assessment
```

Exemples :
- Comment tu trouves le dataset ?
- Que penses-tu de ces données ?
- Ton avis sur le dataset ?
- Le dataset est-il propre ?
- Comment est la qualité de ce dataset ?

Aucun outil n'est relancé pour cette intention.

La réponse utilise uniquement les faits déjà calculés par DataVision.

## 3. Context Engine enrichi

Le contexte inclut maintenant :
- datasetName ;
- rowCount ;
- columnCount ;
- duplicateCount ;
- missingCells ;
- qualityScore ;
- qualityIssuesCount ;
- numericColumnCount ;
- categoricalColumnCount ;
- datasetSchema.

Les lignes brutes restent exclues de cette couche.

## 4. Principe de performance

Les questions conversationnelles courantes doivent suivre :

```text
Question
  ↓
Intent déterministe
  ↓
Réponse à partir du contexte déjà calculé
```

et non :

```text
Question
  ↓
Nouvelle analyse
  ↓
Profiling
  ↓
Réponse
```

Le Model Gateway est réservé aux demandes réellement ambiguës ou complexes.
