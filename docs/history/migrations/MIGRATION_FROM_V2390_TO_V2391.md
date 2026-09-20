# Migration v2.39.0 → v2.39.1

Correctif ciblé pour **Gouverner → CDC & Acceptance**.

## Cause

L'API Docker était construite avec `backend/` comme contexte et n'embarquait donc pas
`compliance/CDC_COVERAGE_MATRIX.json`. En parallèle, le navigateur appelait directement
`http://localhost:8005`, ce qui rendait l'UI sensible aux problèmes de port/CORS/hostname.

## Correctifs

- image API construite depuis la racine du dépôt ;
- dossier `compliance/` embarqué sous `/app/compliance` ;
- résolution robuste de `DATAVISION_PROJECT_ROOT` ;
- frontend API en same-origin `/api/backend` ;
- rewrite Next.js vers `http://api:8005/api/v1` dans Docker ;
- bouton de retry et diagnostic dans CDC & Acceptance.

## Reconstruction

```powershell
.\preflight-windows.ps1
.\reset-docker.ps1
.\rebuild-windows.ps1
```
