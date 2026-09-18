# Validation — v2.9.0

## Backend

```text
pytest -q : 52 passed
python compileall : OK
```

Nouveaux scénarios couverts :

- télémétrie HTTP par workspace ;
- agrégation d’usage par feature ;
- overview SLO ;
- création d’une suite AI Analyst ;
- ajout d’un cas avec attentes ;
- exécution gouvernée d’un benchmark ;
- scoring exact des checks ;
- persistance des résultats ;
- retry Redis avec backoff ;
- passage `retry_wait → queued → failed` lorsque les retries sont épuisés ;
- historique séparé des tentatives.

## Frontend

```text
TS/TSX transpilation --noCheck : OK
strictNullChecks ciblé avec stubs : OK
```

Le `next build` complet n’est pas revendiqué comme validé dans l’environnement de génération, car les dépendances npm ne sont pas présentes localement. Il reste à confirmer sur la machine Docker cible.

## Limites

- la collecte provider-native de tokens/coûts reste partielle tant qu’un LLM externe instrumenté n’est pas configuré ;
- les SLO historiques sont calculés à partir des événements conservés dans le metadata store, sans backend Prometheus/OpenTelemetry externe ;
- les notifications sortantes gouvernées restent à ajouter.
