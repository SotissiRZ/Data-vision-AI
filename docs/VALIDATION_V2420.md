# Validation v2.42.0 — Data Preparation Completion

La v2.42.0 ferme le lot **Data Preparation** du roadmap DataVision avec un gate exécutable dédié.

## Périmètre livré

- jointures `inner`, `left`, `right`, `outer` sur une ou plusieurs clés ;
- concaténation verticale (`inner` / `outer`) et horizontale avec résolution déterministe des collisions de noms ;
- `groupby` avec plusieurs agrégations dans une même étape ;
- pivot et unpivot/melt ;
- feature engineering existant conservé : one-hot, standardisation, Min-Max, expressions calculées sûres, composantes temporelles ;
- nouveau binning numérique : quantiles ou largeur égale ;
- nouvelles variables retardées (`lag`) avec regroupement et ordre optionnels ;
- nouvelles fenêtres glissantes (`rolling`) : mean, sum, min, max, median, std ;
- pipelines multi-datasets persistables et rejouables ;
- dépendances secondaires explicites et remplaçables par binding ;
- validation complète en mémoire d'un pipeline avant création de versions persistées.

## Gate exécutable

```bash
python scripts/preparation_acceptance.py --root . --check
```

Le manifest `compliance/PREPARATION_ACCEPTANCE.json` exige 8/8 éléments et pointe vers les preuves code/tests.

## Non-régression

Les tests v2.42 couvrent :

- feature engineering avancé ;
- jointures multi-clés ;
- agrégations multiples ;
- replay multi-dataset ;
- remplacement d'une dépendance secondaire ;
- validation sans persistance ;
- absence de branche partielle lorsqu'une étape tardive échoue ;
- exposition frontend des capacités v2.42.
