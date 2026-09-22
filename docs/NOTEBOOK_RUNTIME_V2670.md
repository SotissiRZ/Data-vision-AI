# DataVision AI v2.67 — Notebook Runtime persistant

## Architecture

Chaque notebook possède un identifiant de session déterministe séparé pour Python et R. Le sandbox maintient un processus kernel vivant par session. Les datasets gouvernés sont réinjectés à chaque exécution sous `df`/`dataset` (Python) ou `data`/`dataset` (R), tandis que les autres variables utilisateur restent dans le namespace du kernel.

## Reprise

Un redémarrage du sandbox détruit volontairement l’état mémoire. DataVision conserve le suivi de génération et signale l’état `reset/lost`. L’utilisateur peut reconstruire l’état par **Redémarrer + reconstruire**, qui réexécute le notebook dans l’ordre.

## Environnements

Les dépendances Python/R sont déclarées par notebook et validées contre l’inventaire du sandbox. Un lock de versions est stocké. L’installation dynamique réseau est désactivée (`image-managed`) afin d’éviter les dérives et de garder un runtime reproductible.

## Sécurité

Le sandbox reste sur réseau interne, non exposé, non-root, `read_only`, capabilities supprimées. Les kernels héritent des limites mémoire/fichiers/processus et un timeout de cellule termine le kernel concerné.
