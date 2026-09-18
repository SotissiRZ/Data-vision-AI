# DataVision AI — v0.9.2

DataVision AI est un **logiciel installable de Data Intelligence** réunissant import, profiling, qualité, préparation versionnée, statistiques, SQL local, visualisation, Machine Learning, forecasting, détection d'anomalies, explicabilité, prédiction et maintenant **AI Analyst orchestré** dans une même interface.

L'interface conserve l'esprit du DataVision R/Shiny historique — navigation latérale, modules analytiques dédiés et résultats structurés — avec une architecture moderne **Next.js + FastAPI + Python**.

## Ports de cette version

Les ports par défaut ont été déplacés pour éviter les conflits demandés :

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

Les ports 3000 et 8000 ne sont plus utilisés par la configuration Docker fournie.


## Correctif v0.9.2 — build Docker / TypeScript

Cette révision corrige le blocage rencontré pendant `next build` :

```text
Type error: 'result' is possibly 'null'.
frontend/app/page.tsx
```

Le correctif ajoute des assertions de non-nullité uniquement dans les handlers asynchrones exécutés après le garde UI `if (!result) return ...`. Les modules concernés sont Préparation, Régression, ANOVA, ACP, Clustering, tests statistiques, visualisation, SQL, forecasting, anomalies et AI Analyst.

Le warning Autoprefixer `align-items: end` a aussi été supprimé en utilisant `align-items: flex-end`.

Sur une machine où l'étape `npm install` de l'image Docker a déjà été construite, Docker doit normalement réutiliser cette couche en cache lors du prochain build du frontend.

## Nouveautés v0.9 — AI Analyst réel

### 1. Orchestrateur analytique

Le nouvel onglet **AI Analyst** accepte une demande en français ou en anglais et :

1. détecte l'intention analytique ;
2. inspecte le dataset ;
3. construit un plan ;
4. sélectionne des outils réels ;
5. exécute les calculs ;
6. transforme les sorties en constats vérifiables ;
7. exécute un contrôle Critic ;
8. retourne la provenance des résultats.

Le noyau v0.9 fonctionne **sans fournisseur LLM externe**. Il utilise un routeur déterministe de langage naturel pour choisir les moteurs analytiques. Une couche LLM configurable pourra être ajoutée ensuite pour enrichir la compréhension du langage, sans lui déléguer les calculs numériques.

### 2. Tool Registry

Outils actuellement orchestrables :

- profiling ;
- Data Quality ;
- corrélations ;
- régression ;
- ANOVA ;
- clustering ;
- AutoML ;
- forecasting ;
- détection d'anomalies ;
- decision support.

### 3. Intentions prises en charge

Exemples :

```text
Analyse ce dataset et identifie les principaux problèmes, relations et anomalies.
Quelles sont les corrélations les plus importantes ?
Détecte les anomalies dans les variables numériques.
Compare les groupes et indique s'il existe une différence significative.
Fais une régression pour expliquer target par x et z.
Construis un modèle prédictif pour churn.
Prévois sales sur les 12 prochaines périodes.
```

La cible, la colonne temporelle et l'horizon peuvent aussi être forcés dans l'interface.

### 4. Critic / Reliability Layer

Chaque exécution vérifie au minimum :

- le succès ou l'échec de chaque outil ;
- la présence d'une provenance pour les constats numériques ;
- l'interdiction d'utiliser un LLM comme calculatrice.

Le résultat comprend un statut `passed` ou `warning`.

### 5. Provenance

Chaque réponse AI Analyst contient :

- dataset et version utilisés ;
- date d'exécution ;
- outils réellement exécutés ;
- temps d'exécution par outil ;
- résultats techniques ;
- constats reliés à leur source calculée ;
- politique de calcul `deterministic_tools_only`.

## API v0.9

```text
GET  /api/v1/datasets/{id}/ai/capabilities
POST /api/v1/datasets/{id}/ai/analyze
```

Exemple :

```json
{
  "question": "Quelles sont les corrélations les plus importantes entre age, score et cost ?",
  "variables": ["age", "score", "cost"],
  "mode": "fast"
}
```

Exemple avec forecasting :

```json
{
  "question": "Prévois les ventes sur les 12 prochaines périodes",
  "target": "sales",
  "date_column": "date",
  "horizon": 12,
  "mode": "auto"
}
```

## Fonctionnalités déjà présentes

- CSV / XLSX / JSON / Parquet / TXT ;
- profiling automatique ;
- Data Quality ;
- versioning immuable et rollback ;
- pipelines de préparation sauvegardables/rejouables ;
- feature engineering sécurisé ;
- GroupBy, pivot, unpivot, jointures et concaténations ;
- régression, ANOVA, ACP, K-means ;
- Statistical Test Advisor ;
- tests paramétriques/non paramétriques et corrélations ;
- Visualization Studio ;
- SQL Workspace read-only ;
- DuckDB / Polars ;
- AutoML, CV, tuning et train/validation/test ;
- guardrails ML ;
- Model Cards et registre local ;
- prédictions ;
- forecasting ;
- anomalies ;
- XAI global/local ;
- AI Analyst avec orchestration d'outils, Critic et provenance.

## Validation v0.9

Backend :

```text
12 passed
```

Les nouveaux scénarios v0.9 vérifient :

- endpoint des capacités AI Analyst ;
- routage d'une demande de corrélation ;
- exécution réelle du moteur de corrélation ;
- provenance des résultats ;
- `llm_used_for_numeric_calculation = false` ;
- exécution d'une régression demandée en langage naturel ;
- R² provenant réellement du moteur statistique.

Compilation Python : `OK`.

## Lancer avec Docker

```bash
cp .env.example .env
docker compose up --build
```

Puis ouvrir :

```text
Interface : http://localhost:3005
API       : http://localhost:8005
OpenAPI   : http://localhost:8005/docs
```

## Tests

```bash
cd backend
PYTHONPATH=. pytest -q
```

## Documentation incluse

```text
docs/
├── AI_ANALYST.md
├── ARCHITECTURE.md
├── CHANGELOG.md
├── FORECASTING_ANOMALY_XAI.md
├── ML_AUTOML.md
├── README_DEVELOPPEMENT.md
├── ROADMAP_EXECUTION.md
└── VALIDATION.md
```

## Limites explicites de v0.9

- le routeur de langage naturel est déterministe : un LLM configurable n'est pas encore nécessaire au fonctionnement du module ;
- NLQ/Text-to-SQL général reste `partial` ;
- SHAP complet reste `partial` ;
- rapports reproductibles, authentification/workspaces et packaging desktop renforcé restent à développer.

## Règle de fiabilité

Le LLM n'effectue jamais lui-même les calculs statistiques, ML ou de forecasting. Les nombres proviennent des moteurs déterministes ; toute couche IA conversationnelle future restera limitée à la compréhension, la planification, l'orchestration et l'explication.
