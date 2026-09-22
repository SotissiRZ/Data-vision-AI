# Report Intelligence — DataVision AI v1.2.0

## Objectif

Report Intelligence ajoute une couche éditoriale déterministe au Professional Report Studio. Son rôle est d’organiser des résultats déjà calculés, de sélectionner des visualisations pertinentes et de produire une lecture structurée sans transformer un LLM en moteur statistique.

## Workflow

```text
Dataset versionné
   ↓
Profiling + qualité + statistiques
   ↓
Sélection des constats vérifiables
   ↓
Hiérarchisation des résultats
   ↓
Sélection/génération des figures
   ↓
Limites et précautions
   ↓
Rapport PDF / DOCX / HTML / Markdown
```

## Intelligence éditoriale

Le Report Studio expose trois contrôles :

- **Narration analytique automatique** : active la section de lecture analytique ;
- **Sélection intelligente des graphiques** : autorise le moteur à compléter les visualisations épinglées par des figures calculées ;
- **Nombre maximal de figures** : limite la densité visuelle du rapport.

## Résultats clés

Les constats sont hiérarchisés et contiennent :

- un rang ;
- un titre ;
- un constat ;
- une preuve issue du moteur de calcul ;
- une interprétation prudente.

Les familles actuellement couvertes comprennent la qualité, la complétude, les corrélations numériques, l’asymétrie des distributions, la concentration des catégories, les tendances temporelles et, si elle est explicitement sélectionnée, une session AI Analyst.

## Figures automatiques

Selon le schéma du dataset, le moteur peut proposer :

1. bar chart des valeurs manquantes ;
2. heatmap de corrélation ;
3. scatterplot de la relation numérique la plus forte ;
4. histogramme d’une variable informative ;
5. comparaison d’une mesure selon une catégorie ;
6. évolution temporelle d’une mesure.

Chaque figure automatique est intégrée directement au rapport, sans polluer le registre des visualisations sauvegardées. Elle contient `source=auto_report`, une justification, une lecture et la version du dataset.

## Précautions d’interprétation

Le moteur crée une section dédiée lorsqu’une limite est détectée :

- données manquantes ;
- qualité insuffisante ;
- petit échantillon ;
- colonnes identifiantes ;
- limites de temporalité ;
- absence de causalité démontrée ;
- absence d’analyse AI Analyst lorsque pertinente.

Les associations statistiques ne sont jamais reformulées comme des relations causales.

## Détection des identifiants

La règle v1.2 évite de traiter toute variable continue quasi unique comme un identifiant. Sont prioritairement exclues les colonnes dont le nom indique une fonction d’identification : `id`, `*_id`, UUID, clé, code, numéro d’enregistrement, etc. Une mesure continue unique peut donc rester disponible pour les corrélations et visualisations automatiques.

## Reproductibilité

Le rapport sauvegarde :

- l’identifiant et la version du dataset ;
- le mode de génération (`intelligent` ou `manual`) ;
- les options d’intelligence éditoriale ;
- les visualisations sauvegardées sélectionnées ;
- les visualisations automatiques intégrées ;
- la session AI Analyst choisie ;
- la structure des sections ;
- la date de génération.

## API

`POST /api/v1/datasets/{dataset_id}/reports`

Exemple :

```json
{
  "title": "Rapport analytique",
  "template": "analytical",
  "auto_story": true,
  "auto_visualizations": true,
  "max_visualizations": 6,
  "visualization_ids": []
}
```

## Validation

- 19 tests backend ;
- `python -m compileall backend/app` : OK ;
- exports PDF/DOCX rendus et inspectés sur 13 pages ;
- transpilation syntaxique du frontend : OK.

Le build complet Next.js/Docker doit toujours être validé sur la machine cible.
