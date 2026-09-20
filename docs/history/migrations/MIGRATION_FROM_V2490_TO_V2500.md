# Migration v2.49.0 → v2.50.0

Aucune migration destructive de données n'est requise.

## Changements

- nouveau service `automl_engine.py` au-dessus du moteur supervisé historique ;
- endpoints AutoML compatibles, avec support `task=clustering`, `features` et historique d'expériences ;
- nouvelles routes `/models/experiments` ;
- contrats Assistant alignés sur classification/régression/clustering ;
- sidebar compact par défaut et étendu au survol/focus.

Les modèles et rapports existants restent compatibles. Les volumes Docker ne doivent pas être supprimés.
