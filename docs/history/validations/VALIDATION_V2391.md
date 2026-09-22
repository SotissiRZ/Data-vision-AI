# Validation v2.39.1

Correctif ciblé de **Gouverner → CDC & Acceptance**.

## Régressions corrigées

- la matrice CDC est maintenant copiée dans l'image backend ;
- le service CDC résout correctement la racine en source et dans Docker ;
- les appels frontend passent par un proxy same-origin `/api/backend` ;
- l'UI CDC affiche un diagnostic et un bouton de nouvelle tentative.

## Contrats attendus

- `/api/v1/system/cdc-compliance` répond depuis le conteneur API ;
- `/api/v1/system/production-acceptance` répond depuis le conteneur API ;
- le navigateur n'a plus besoin de contacter directement le port 8005 pour les appels applicatifs.
