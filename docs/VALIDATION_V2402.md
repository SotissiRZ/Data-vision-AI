# Validation v2.40.2

## Motif de la release

Après correction du narrowing de `model` en v2.40.1, le build Docker/Next atteignait le contrôle TypeScript suivant et échouait sur `app/page.tsx:1024` : un objet `AnyObj` était transmis à `runModelCounterfactuals()` alors que l’API exige un payload contenant obligatoirement `row: Record<string, unknown>`.

## Correction

`XaiView.runCf()` :

- parse la ligne JSON en `Record<string, unknown>` ;
- dérive le type du payload directement depuis `runModelCounterfactuals` avec `Parameters<typeof runModelCounterfactuals>[1]` ;
- conserve `activeModel` pour le narrowing non nul dans les callbacks asynchrones.

Cette stratégie évite de dupliquer manuellement le contrat de l’API dans la vue et fait échouer le typecheck si la signature de l’API change de manière incompatible.

## Contrôles inclus

- production baseline ;
- repository hygiene ;
- audit CDC ;
- suite backend ;
- test de non-régression du payload XAI ;
- vérification cryptographique de l’archive de release.

## Validation machine cible

Relancer :

```powershell
docker compose down
docker compose up -d --build
docker compose ps
```

Les avertissements Autoprefixer `start/end` observés dans le build ne sont pas des erreurs bloquantes.
