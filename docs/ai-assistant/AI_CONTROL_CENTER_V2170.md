# DataVision v2.17.0 — AI Control Center

## UI

Le module est accessible dans :

```text
Gouverner → IA & Modèles
```

Il expose :
- politique de confidentialité ;
- activation du Model Gateway ;
- providers ;
- tests de connexion ;
- routes par tâche ;
- ordre de fallback ;
- budget mensuel ;
- télémétrie de coût/tokens.

## Secret management

Les clés ne sont pas enregistrées dans le profil provider.

En mode Entreprise :

```text
provider → secret_id → Secret Vault v2.12
```

En mode local :

```text
provider → nom de variable d'environnement
```

## Hybrid NLU

Le routeur déterministe reste prioritaire.

Le Model Gateway n'est consulté qu'en cas d'intention `unknown` et seulement
si le mode `gateway` est activé.

La réponse structurée est validée par Pydantic et doit appartenir à une liste
fermée d'intentions DataVision.

## Grounded conversation

Les questions explicatives peuvent utiliser le provider `explanation`.

Le prompt reçoit :
- contexte sémantique ;
- schéma des colonnes si autorisé ;
- dernier résumé de résultats déterministes.

Il ne reçoit jamais de lignes brutes via cette couche.
