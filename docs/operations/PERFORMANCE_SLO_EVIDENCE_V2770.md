# DataVision AI v2.77.0 — Performance & SLO Evidence

## Objectif

La v2.77 ferme le gap CDC §59 avec une chaîne de preuve reproductible qui distingue explicitement :

1. **benchmark local de non-régression** — vérifie le moteur et des budgets d’ingénierie sur l’hôte courant ;
2. **preuve de charge externe** — mesure une cible HTTPS réelle avec concurrence, durée et volume minimums ;
3. **évaluation gouvernée** — compare les métriques brutes au fichier versionné `policies/performance_slo.json` ;
4. **ledger par workspace** — conserve le payload, son statut et son SHA-256 dans le metadata store.

Un benchmark local n’est jamais présenté comme une preuve de capacité production.

## Budgets versionnés

Le profil `local_smoke` couvre les requêtes metadata, un groupby pandas déterministe, la sérialisation JSON, le taux d’erreur et le débit d’opérations. Il sert de garde de non-régression rapide.

Le profil `production_standard` exige au minimum :

- 500 requêtes ;
- 30 secondes de charge ;
- concurrence >= 5 ;
- cible HTTPS non locale ;
- p50 <= 300 ms ;
- p95 <= 750 ms ;
- p99 <= 1500 ms ;
- erreurs <= 1 % ;
- débit >= 20 req/s.

Ces valeurs sont des défauts d’ingénierie versionnés. Un déploiement peut les durcir. Les résultats mesurés restent attachés à leur environnement et ne constituent pas une certification universelle de capacité.

## Générer une preuve sur l’infrastructure cible

Depuis une machine de charge distincte de la cible :

```bash
python scripts/performance_benchmark.py \
  --target https://datavision.example.com/ready \
  --duration 60 \
  --concurrency 25 \
  --max-requests 5000 \
  --profile production_standard \
  --output evidence/performance-prod.json
```

Le fichier généré utilise le schéma `datavision.performance-evidence/v1` et contient les latences p50/p95/p99, le taux d’erreur, le débit, le volume, l’environnement du runner et un SHA-256 canonique.

## Import gouverné

L’API Entreprise expose :

- `GET /api/v1/workspaces/{workspace_id}/operational/performance` ;
- `POST /api/v1/workspaces/{workspace_id}/operational/performance/benchmark` ;
- `POST /api/v1/workspaces/{workspace_id}/operational/performance/evidence` ;
- `GET /api/v1/workspaces/{workspace_id}/operational/performance/runs`.

L’import recalcule l’intégrité, ignore les budgets éventuellement fournis par le client au profit de la politique versionnée, puis vérifie la cible, le volume, la durée, la concurrence et toutes les métriques SLO.

## Statuts production

Le cockpit peut afficher :

- `not_evidenced` — aucune preuve cible valide importée ;
- `passed` — dernière preuve production conforme et non périmée ;
- `failed` — preuve production présente mais budgets non respectés ;
- `stale` — preuve trop ancienne selon la politique.

La preuve locale reste visible séparément avec la mention explicite qu’elle ne remplace pas une mesure sur l’infrastructure cible.

## Reproductibilité et intégrité

Chaque run persisté conserve : profil, contexte, cible, métriques, budgets appliqués, violations, environnement, runner, timestamps et SHA-256. Les preuves externes conservent aussi `source_artifact_sha256`, distinct de l’empreinte du record enrichi par DataVision.

Le gate `PERFORMANCE_SLO_ACCEPTANCE` vérifie automatiquement la présence du policy-as-code, du ledger, du runner externe, des API gouvernées, du cockpit UI, des tests et de cette documentation.
