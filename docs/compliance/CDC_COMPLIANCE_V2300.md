# DataVision v2.30.0 — CDC Compliance & Production Acceptance

## Objectif

Transformer le CDC en contrôle continu plutôt qu'en document passif.

## Source de vérité

`compliance/CDC_COVERAGE_MATRIX.json` contient 75 entrées, une par section du
CDC 1.0.

## Statuts

| Statut | Score | Définition |
|---|---:|---|
| implemented | 1.0 | fonctionnalité réellement présente avec preuve dépôt |
| partial | 0.5 | fondation réelle mais exigence non totalement couverte |
| missing | 0.0 | exigence non implémentée |

## Résultat v2.30

- 52 implémentées ;
- 23 partielles ;
- 0 entièrement manquantes ;
- 84,7 % de couverture pondérée.

## P0 ouverts

### §46 Security

Restent notamment :
- MFA/WebAuthn ;
- antivirus d'upload ;
- gestion de clés externe plus complète.

### §71 Critères d'acceptation

Le pipeline CI est défini mais sa réussite doit être observée sur le dépôt et
l'infrastructure cibles. Les tests de charge/SLO et l'acceptance utilisateur
restent à signer.

### §74 Definition of Done

Le DoD code/test/package est automatisé. La signature production réelle reste
conditionnelle aux contrôles externes ci-dessus.

## CI

`scripts/cdc_audit.py --check` vérifie que toutes les preuves référencées
existent encore. Il ne transforme jamais automatiquement un statut `partial`
en `implemented`.

## API

- `/api/v1/system/cdc-compliance`
- `/api/v1/system/production-acceptance`

## Règle de vérité

Le produit ne doit jamais afficher 100 % tant qu'une section est `partial` ou
`missing`, même si l'interface principale est fonctionnelle.
