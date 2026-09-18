# Validation v2.1.0

## Backend

Suite de tests : **25 tests passants**.

Les nouveaux scénarios v2.1 couvrent :

- bootstrap du premier propriétaire ;
- bearer token et `/auth/me` ;
- création de workspace ;
- liaison d'un dataset ;
- création de politique colonnes/lignes ;
- provisionnement d'un analyste ;
- application réelle de la politique dans `governed-preview` ;
- refus RBAC d'une action de gouvernance par un analyste ;
- journal d'audit ;
- reconnexion ;
- soumission d'un job ;
- mise en file Redis simulée ;
- listing des jobs ;
- annulation d'un job en file.

## Frontend

- transpilation syntaxique TypeScript/TSX : OK ;
- nouvelle zone `Gouverner` : ajoutée ;
- API Enterprise : ajoutée ;
- responsive CSS Governance Center : ajouté.

Le build Docker/Next.js complet doit être confirmé dans l'environnement utilisateur, comme pour les versions précédentes.
