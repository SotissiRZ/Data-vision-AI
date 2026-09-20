# Migration v2.51.0 → v2.52.0

Migration additive. Aucun format de modèle existant n'est supprimé.

- les anciens endpoints XAI restent compatibles ;
- les diagnostics ajoutent des champs de provenance, stabilité et métriques par classe ;
- les contre-factuels acceptent de nouveaux paramètres optionnels de contraintes ;
- `xai_summary` est ajouté à la Model Card lors d'un audit XAI persisté ;
- le Report Builder lit ce résumé lorsqu'il existe.
