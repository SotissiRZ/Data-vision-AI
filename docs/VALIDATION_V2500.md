# Validation DataVision AI v2.50.0

## Portée

v2.50.0 ferme le lot AutoML prévu dans la roadmap immédiate : classification, régression et clustering partagent désormais un contrat unique, un leaderboard, une métrique de sélection explicite et un historique d'expériences persistant. Le forecasting reste dans son moteur spécialisé et sera durci avec le lot forecasting/anomaly.

La version ajoute également le sidebar dynamique demandé : icônes en mode compact, expansion au survol ou au focus clavier, sans déplacement du contenu principal.

## Garde-fous

- aucune sélection du meilleur modèle sur le test final supervisé ;
- cible interdite dans la liste explicite des features ;
- clustering sans cible supervisée ni faux jeu de test ;
- variables identifiantes probables exclues du clustering ;
- métriques de clustering internes et limites métier documentées ;
- benchmark seul ne persiste pas de modèle final ;
- chaque expérience conserve dataset/version, métrique, leaderboard, sélection et justification.

## Gate

```text
python scripts/automl_acceptance.py --root . --check
```

Le gate couvre 8 exigences et exécute les tests backend/frontend v2.50.0.
