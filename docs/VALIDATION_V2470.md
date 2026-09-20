# Validation v2.47.0 — NLQ + Semantic Layer

La v2.47.0 conserve le moteur sémantique interne v2 pour compatibilité et ajoute une couche de gouvernance métier autour de lui.

## Contrat

- métriques/dimensions : définition métier, unité, synonymes, certification, `allowed_roles` ;
- relations multi-tables validées et tracées ;
- glossaire lié à une métrique/dimension ;
- NLQ résolu contre le modèle sémantique avant fallback SQL ;
- refus 403 lorsqu'une question tente d'accéder à un objet sémantique interdit ;
- sortie vérifiable : terme reconnu, modèle, tables, relations, rôle, SQL/plan read-only.

## Gate

`python scripts/semantic_acceptance.py --check` doit retourner `8/8`.
