# Validation — DataVision AI v0.9.1

## Backend

Commande :

```bash
cd backend
PYTHONPATH=. pytest -q
```

Résultat obtenu :

```text
............
12 passed
```

## Compilation Python

```bash
python -m compileall -q app
```

Résultat : `OK`.

## Nouveaux scénarios v0.9

Les tests automatisés ajoutés couvrent :

- `GET /ai/capabilities` ;
- présence du Tool Registry ;
- détection d'une intention `correlation` ;
- exécution réelle du moteur de corrélation ;
- Critic `passed` ;
- provenance dataset/version/outils ;
- politique `llm_used_for_numeric_calculation = false` ;
- détection d'une intention `regression` ;
- exécution réelle de la régression ;
- R² supérieur à 0,95 sur un jeu de test construit pour vérifier le moteur.

## Ports

```text
Frontend : 3005
Backend  : 8005
```

## Frontend

Correctif v0.9.1 appliqué au type narrowing TypeScript des handlers asynchrones (`result` nullable) qui bloquait `next build` à `page.tsx:321`. Les usages analogues ont été corrigés dans les autres modules afin d'éviter une succession d'erreurs identiques.

Contrôle statique avec stubs React/Node : aucune erreur TypeScript propre au code DataVision détectée après le correctif.

Le build Next.js complet n'a pas pu être reproduit dans l'environnement de génération car l'installation npm y a dépassé le délai disponible. La validation définitive du conteneur frontend doit donc être faite par `docker compose build web` sur la machine cible.


## v0.9.2

- Correctif appliqué pour l’erreur TypeScript `model is possibly null` signalée par `next build`.
- Vérification statique ciblée des autres fermetures asynchrones manipulant `result`/`model`.
- Le build Next.js complet doit être exécuté dans Docker sur la machine cible, où les dépendances npm sont disponibles.
