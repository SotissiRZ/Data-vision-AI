# DataVision AI v2.2 — Tenant-Aware Data Access

## Objectif

La v2.2 transforme les policies de v2.1 en véritable boundary de données. Une session Enterprise active ne doit jamais pouvoir appeler une ancienne route analytique et récupérer le dataset brut par accident.

## Principe

Le backend utilise un `ContextVar` par requête. Le middleware lit `Authorization` et `X-Workspace-ID`, valide l'utilisateur, le rôle et le workspace, puis injecte le contexte dans toute la chaîne d'exécution.

`storage.load_dataframe(dataset_id)` est désormais le point d'enforcement universel. En mode Enterprise il vérifie :

1. permission RBAC ;
2. appartenance du dataset au workspace ou à sa lignée ;
3. policies héritées de la lignée ;
4. filtres de lignes ;
5. projection des colonnes autorisées.

Le DataFrame remis aux services analytiques est donc déjà gouverné.

## Permission mapping

- lecture / metadata / profile / quality / history : `dataset:read` ;
- analyses, SQL, NLQ, visualisations, XAI, AI Analyst : `analysis:run` ;
- entraînement / AutoML : `model:run` ;
- transformations / pipelines / semantic authoring : `dataset:write` ;
- dashboards, visualisations sauvegardées et rapports : `publish:write`.

Le mode local demeure compatible lorsque aucun header Enterprise n'est présent.

## RLS avant CLS

Les filtres de lignes sont évalués avant la suppression de colonnes. Ceci évite une faille classique où la colonne nécessaire au filtre disparaît avant l'évaluation du filtre.

Une policy incohérente échoue fermée : colonne de filtre absente ou opérateur inconnu produit une erreur au lieu d'un accès élargi.

## Lineage et versions

L'accès à une lignée est accordé si une version de cette même racine est liée au workspace. Les versions dérivées créées sous contexte Enterprise sont automatiquement liées au workspace.

Les policies remontent la chaîne `child -> parent -> root` et sont combinées de façon restrictive.

### Materialized RLS snapshot

Lorsqu'une transformation est effectuée sur un DataFrame déjà filtré par RLS, les lignes sauvegardées sont déjà restreintes. DataVision enregistre les couples `(policy_id, updated_at)` ayant participé à cette matérialisation.

À la lecture d'une version dérivée :

- si la policy est inchangée, son filtre de lignes déjà matérialisé n'est pas rejoué ;
- sa sécurité colonne reste appliquée ;
- si la policy a été modifiée, le nouveau filtre est réévalué.

Cette logique évite de rendre illisible une version sécurisée après suppression volontaire d'une colonne utilisée uniquement comme filtre RLS.

## Background jobs

Le worker reconstruit le contexte à partir du `user_id` et du `workspace_id` stockés avec le job. AutoML, AI Analyst, forecasting et rapports reçoivent donc le même DataFrame gouverné que les appels synchrones.

## Frontend

`frontend/lib/api.ts` possède un wrapper `apiFetch()` qui attache automatiquement le token et le workspace actif à chaque appel. La présence du boundary est visible dans l'interface via le badge `Accès gouverné`.

## Limitations restantes

- pas encore d'OIDC/SSO ni refresh token ;
- pas de RLS native PostgreSQL sur les fichiers locaux : l'enforcement est applicatif ;
- un modèle déjà entraîné avant une modification de policy n'est pas encore invalidé automatiquement ;
- SHAP/fairness complets restent partiels ;
- annulation préemptive des calculs déjà lancés reste partielle.
