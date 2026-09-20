# Validation v2.40.4

## Objet

Corriger le blocage TypeScript du Feature Store révélé par le build Docker/Next réel de la v2.40.3.

## Correctifs

- `frontend/components/FeatureServingView.tsx` : normalisation de `columns` en `AnyObj[]`.
- `columnNames` est déclaré comme `string[]`.
- les trois rendus `columnNames.map(...)` utilisent un paramètre `name: string`.
- test de garde frontend dédié.

## Contrôles attendus

- production baseline : PASS
- repository hygiene : PASS
- CDC audit : aucune preuve manquante
- tests backend : PASS
- build Docker/Next : à confirmer sur la machine cible avec `docker compose up -d --build`

Les avertissements CSS Autoprefixer restent non bloquants et sont traités séparément.
