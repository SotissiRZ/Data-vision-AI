# DataVision AI v2.76.0 — Workspace Environments & Reproducibility

## Objectif

La v2.76 rend les environnements Python/R reproductibles au niveau du workspace sans autoriser d'installation arbitraire dans le processus principal DataVision. Le modèle privilégie la sécurité et la reproductibilité : les dépendances sont déclarées, résolues contre l'image sandbox approuvée, verrouillées puis référencées par une empreinte SHA-256.

## Hiérarchie

1. **Workspace manifest** : dépendances Python/R communes, policy de sécurité, versions résolues et empreinte canonique.
2. **Notebook overlay** : dépendances supplémentaires ou contraintes plus précises pour un notebook.
3. **Effective manifest** : fusion déterministe workspace + notebook, lock exact et empreinte stockée dans la provenance des runs Python/R.

Une contrainte notebook portant sur le même package remplace la contrainte workspace pour ce notebook uniquement. Le workspace reste inchangé.

## Reproductibilité

Le manifest canonique ne contient aucun timestamp. Son SHA-256 dépend uniquement du scope, des exigences, des versions verrouillées et de la policy. La vérification compare les versions verrouillées à l'inventaire courant du sandbox et signale toute dérive.

Les runs Python/R enregistrent :

- l'empreinte de l'environnement effectif ;
- l'empreinte du manifest workspace ;
- les locks Python et R ;
- l'indicateur de reproductibilité.

## Isolation et sécurité

- isolation par workspace dans le sandbox ;
- installation réseau dynamique désactivée ;
- aucune installation de package dans le runtime API principal ;
- modification du manifest workspace réservée à `workspace:manage` en mode Entreprise ;
- invalidation des kernels suivis lorsqu'un manifest workspace ou notebook change ;
- mode local conservé avec le même format de manifest.

Les images sandbox restent administrées par l'opérateur. Pour ajouter un package absent, l'image doit être reconstruite et approuvée ; DataVision ne contourne pas ce contrôle par `pip install`, `install.packages()` ou Conda réseau à la volée.

## API

- `GET /api/v1/notebooks/workspace-environment`
- `PUT /api/v1/notebooks/workspace-environment`
- `POST /api/v1/notebooks/workspace-environment/sync`
- `POST /api/v1/notebooks/workspace-environment/verify`
- endpoints notebook `/environment` existants conservés pour l'overlay.

## UX

Notebook Studio expose séparément le socle workspace et l'overlay notebook, avec statut, locks, reproductibilité et préfixe de l'empreinte SHA-256.
