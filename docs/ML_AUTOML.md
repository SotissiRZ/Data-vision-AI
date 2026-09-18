# ML / AutoML — v0.7

## But

Fournir une première couche AutoML vérifiable, reproductible et suffisamment prudente pour servir de moteur au futur AI Analyst.

## Workflow

1. validation de la cible ;
2. suppression des lignes sans cible ;
3. détection classification/régression ;
4. guardrails ;
5. split reproductible 60/20/20 ;
6. cross-validation sur le train ;
7. benchmark ;
8. sélection sur validation ;
9. tuning contrôlé sur le train ;
10. contrôle sur validation ;
11. refit train + validation ;
12. évaluation unique sur test final ;
13. permutation importance ;
14. sauvegarde du modèle et de la Model Card.

## Guardrails actuels

- échantillon < 100 ;
- class imbalance ;
- identifiants / quasi-identifiants ;
- constantes ;
- colonnes temporelles ;
- corrélation absolue >= 0.995 avec une cible numérique.

Ces règles signalent des risques ; elles ne doivent pas être interprétées comme une décision métier automatique.

## Modèles

Voir `backend/app/services/modeling.py` pour la liste exacte des algorithmes et grilles de tuning.

## Artifacts

```text
DATA_ROOT/models/<model_id>.joblib
DATA_ROOT/models/<model_id>.card.json
```

La Model Card contient la provenance et les limites de chaque modèle.
