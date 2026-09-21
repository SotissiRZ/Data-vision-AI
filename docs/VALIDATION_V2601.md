# Validation v2.60.1 — Correctif build frontend

Correctif ciblé du build Docker/Next.js signalé sur `frontend/app/page.tsx`.

## Correctifs

- garde nulle sur `controlPlane?.dataset?.role_matrix` avant `map`;
- alignements flex CSS compatibles Autoprefixer (`flex-start` / `flex-end`);
- `incremental: true` explicite dans TypeScript.

## Compatibilité

Aucune migration de schéma additionnelle. La migration `2.60.0-001` reste valide.
