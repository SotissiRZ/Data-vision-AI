# Proactive Intelligence — v2.5.0

## Objectif

La v2.5 ajoute une couche de **surveillance analytique déterministe** au-dessus du modèle sémantique. DataVision ne se limite plus à répondre à une question : il peut enregistrer des métriques à surveiller, comparer les dernières périodes à l'historique et alimenter une Inbox analytique persistante.

## Surveillances

Une surveillance contient :

- métrique sémantique ;
- dimension temporelle ;
- granularité jour / semaine / mois / trimestre / année ;
- direction surveillée (hausse, baisse, les deux) ;
- seuil de variation ;
- seuil robuste d'anomalie ;
- historique minimum ;
- filtres sémantiques ;
- état actif/inactif.

La configuration automatique crée une surveillance pour chaque métrique certifiée lorsqu'une dimension temporelle exploitable existe.

## Moteur de détection

Le scan combine trois signaux :

1. **Variation de période** : dernière période versus période précédente.
2. **Anomalie de niveau** : score robuste basé sur médiane et MAD, avec repli sur l'écart-type si nécessaire.
3. **Rupture de variation** : comparaison de la variation courante aux variations historiques.

Les niveaux `medium`, `high` et `critical` sont produits par règles déterministes. Le système ne présente pas ces signaux comme des preuves causales.

## Inbox analytique

Chaque alerte persistée contient :

- métrique et période concernées ;
- valeur courante / précédente ;
- variation en pourcentage ;
- scores d'anomalie ;
- preuve textuelle générée à partir des résultats calculés ;
- tendance récente ;
- provenance du moteur et version sémantique ;
- investigations recommandées ;
- statut `open`, `acknowledged`, `resolved` ou `dismissed`.

Un fingerprint empêche la duplication de la même alerte lors de scans répétés sur la même période.

## Investigation guidée

Le moteur propose en priorité des ventilations par dimensions sémantiques certifiées et un contrôle de qualité des données. Ces suggestions sont des pistes d'investigation ; elles n'affirment pas de causalité.

## Sécurité

Les routes v2.5 passent par la boundary tenant-aware v2.2. Les scans synchrones et asynchrones utilisent donc le même contexte RBAC/RLS/column-security que les autres analyses.

## Asynchrone

Le type de job `proactive_scan` est supporté par le worker Redis. La planification calendaire automatique reste `partial` en v2.5 et sera reliée au scheduler Entreprise ultérieurement.
