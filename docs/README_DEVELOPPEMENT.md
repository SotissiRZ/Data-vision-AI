# Guide développeur — DataVision AI v0.9

## Architecture locale

- `frontend/` : Next.js / React / TypeScript.
- `backend/` : FastAPI / Python.
- `backend/app/services/` : moteurs data, statistiques, préparation, visualisation et ML.
- stockage de développement : filesystem configuré par `DATA_ROOT`.

## Services analytiques principaux

### `statistics_engine.py`
Calculs déterministes pour tests statistiques, diagnostics, corrélations et recommandations de tests.

### `data_workspace.py`
Couche SQL locale read-only. DuckDB est le moteur préféré ; SQLite reste uniquement un fallback de runtime hors-ligne quand DuckDB n'est pas importable. Polars est utilisé quand disponible pour la couche dataframe/mémoire.

### `visualization.py`
Prépare les données de visualisation côté backend. Le frontend ne doit pas recalculer les agrégations analytiques.

### `modeling.py` — v0.8
Contient désormais :

- détection classification/régression ;
- preprocessing scikit-learn ;
- split 60/20/20 ;
- validation croisée ;
- benchmark de modèles ;
- tuning contrôlé ;
- garde-fous ML ;
- exclusion AutoML des constantes et identifiants/quasi-identifiants détectés ;
- permutation importance ;
- sauvegarde `.joblib` ;
- Model Cards JSON ;
- registre local ;
- inference.

## Règle ML impérative

Le jeu de test final ne doit jamais être utilisé dans :

- la sélection du modèle ;
- le tuning des hyperparamètres ;
- la validation croisée.

Flux :

```text
train -> CV/tuning
validation -> sélection/contrôle
test final -> métriques finales uniquement
```

Toute modification de ce comportement doit être couverte par des tests.

## Règle SQL

Le SQL utilisateur est limité à `SELECT`/`WITH`. Une seule instruction est autorisée. Les mots-clés destructifs et d'administration sont bloqués avant exécution. Le dataset actif est enregistré comme `dataset`.

## Règle statistique et IA

Toute statistique présentée doit venir de SciPy, statsmodels, scikit-learn ou d'un autre moteur numérique déterministe. Ne pas déléguer les p-values, scores ML, probabilités ou métriques à un LLM.

## Tests

```bash
cd backend
pytest -q
```

Attendu v0.9 :

```text
9 passed
```


### Services v0.9

- `app/services/forecasting.py`
- `app/services/anomaly_detection.py`
- `app/services/xai.py`

Les tests v0.9 sont dans `test_foundation.py`.


## AI Analyst v0.9

Le service `app/services/ai_analyst.py` orchestre les moteurs existants. Toute nouvelle intention doit :

1. résoudre explicitement ses variables ;
2. appeler un moteur calculatoire existant ou un nouveau service testé ;
3. stocker l'exécution dans `executions` ;
4. relier chaque constat à un `evidence.tool` ;
5. laisser le Critic signaler tout échec.

Ports locaux par défaut : frontend `3005`, API `8005`.
