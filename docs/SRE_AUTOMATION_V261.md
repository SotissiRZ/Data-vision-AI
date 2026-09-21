# DataVision AI v2.61 — SRE automatisé & continuité multi-zone

La v2.61 prolonge la couche SRE v2.60 sans casser les endpoints existants.

## Observabilité packagée

Le chart Helm contient désormais un `PrometheusRule` optionnel avec recording rules et alertes pour la disponibilité API, le taux de succès des jobs, la latence P95 et la profondeur de la file Redis. Un ConfigMap Grafana fournit un dashboard SRE/SLO immédiatement importable par un sidecar Grafana standard.

## Routage des alertes

Chaque workspace peut définir plusieurs routes SRE : seuil minimal de sévérité, liste facultative de codes et type d’événement Governed Actions. Sans route explicite, la route historique `sre_slo_breach` reste utilisée.

## Continuité multi-zone

`BACKUP_REPLICATION_TARGETS_JSON` décrit plusieurs cibles S3 compatibles. Chaque cible peut référencer ses secrets par variables d’environnement (`access_key_env`, `secret_key_env`, `session_token_env`). Les résultats sont journalisés individuellement dans `backup_replications`; l’échec d’une zone n’efface pas le statut des autres.

## Exercices DR

Les DR drills sont désactivés par défaut. Ils exigent `SRE_DR_ENABLED=true` et un `APP_ENV` autorisé. Le mode `continuity` exécute un restore drill, contrôle la posture de réplication et lance un probe de récupération. La perte de dépendance est évaluée via un fault model non destructif : aucune base, file Redis ou stockage objet n’est volontairement interrompu par l’application.
