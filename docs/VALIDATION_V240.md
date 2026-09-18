# Validation DataVision AI v2.4.0

## Résultat automatisé

```text
pytest -q
35 passed
```

## Nouveaux scénarios v2.4

1. NLQ multi-table : `CA par catégorie` résout la métrique certifiée et une dimension liée.
2. AI Analyst semantic-first : la requête métier appelle `semantic_query` et expose la provenance.
3. Dashboard sémantique : KPI métier + graphique hiérarchique.
4. Cross-filter sur dimension liée : le filtre affecte également un KPI physique de lignes.
5. Drill-down : `Catégorie → Sous-catégorie` avec conservation du filtre parent.
6. Jointure multi-hop : `Fact → Product → Category` pour agréger une métrique par secteur.
7. Compatibilité : les tests des versions précédentes restent verts.

## Contrôles statiques

```text
Python compileall  : OK
TSX transpilation  : OK
api.ts transpile   : OK
```

## Non déclaré comme validé

Le build Next.js/Docker complet n'a pas été exécuté dans l'environnement de génération. Il doit être validé dans Docker Desktop sur la machine cible.
