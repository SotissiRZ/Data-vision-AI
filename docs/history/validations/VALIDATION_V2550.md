# Validation v2.55.0 — Governance & Control Plane

La v2.55.0 consolide les briques de gouvernance existantes sans créer un second moteur de politiques.

## Nouveautés
- Control Plane workspace unifié.
- Matrice d'accès effective Owner/Admin/Data Scientist/Analyst/Viewer.
- Publication readiness combinant Data Reliability, Trust Center et certifications.
- Digest SHA-256 du journal d'audit récent.
- Snapshots de gouvernance persistants et hashés.
- Politique IA et Model Registry visibles depuis le même plan de contrôle sans exposer les secrets.

## Invariants
- RBAC/RLS/CLS existants restent autoritaires.
- Un dataset non lié au workspace est refusé avant calcul du Control Plane.
- Les snapshots n'accordent aucun droit et ne modifient aucune ressource analytique.
