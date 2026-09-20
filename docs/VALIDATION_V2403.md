# Validation v2.40.3

## Objet

Consolider la null-safety TypeScript du frontend après les builds Docker réels de v2.40.0 à v2.40.2.

## Correctifs

- `frontend/app/page.tsx` : capture `connectorOptions = connectorSpec?.options ?? []` puis utilisation exclusive de cette valeur dans le formulaire connecteur.
- `frontend/components/ComplianceCenter.tsx` : capture `signoffRequired` avant le JSX.
- `frontend/components/ResponsibleAIView.tsx` : capture `activeModel` avant les callbacks asynchrones.
- tests de garde frontend dédiés.

## Contrôles attendus

- production baseline : PASS
- repository hygiene : PASS
- CDC audit : aucune preuve manquante
- tests backend : PASS
- build Docker/Next : à confirmer sur la machine cible avec `docker compose up -d --build`

Les avertissements CSS Autoprefixer ne sont pas des erreurs de compilation et restent traités séparément.
