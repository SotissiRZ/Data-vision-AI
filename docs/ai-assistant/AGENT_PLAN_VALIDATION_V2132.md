# DataVision v2.13.2 — Validation des plans de l'agent

Le LLM ne doit jamais pouvoir transformer directement une phrase en exécution.

Nouveau flux :

```text
Demande utilisateur
      ↓
LLM propose un plan
      ↓
Plan Validator
      ├── outil enregistré ?
      ├── contexte disponible ?
      ├── risque canonique ?
      ├── policy assistant ?
      └── permission DataVision ?
      ↓
Plan validé
      ├── ready
      ├── confirmation_required
      └── deny
      ↓
Exécution via handlers réels
      ↓
Critic / validation
      ↓
Réponse texte + voix
```

## Exemple

Plan proposé :

```json
[
  {"tool": "profile_dataset", "label": "Profiler les données"},
  {"tool": "create_visualization", "label": "Créer les graphiques"},
  {"tool": "export_dataset", "label": "Exporter les résultats"}
]
```

Validation :

```text
profile_dataset       → ready
create_visualization  → ready
export_dataset        → confirmation_required
```

L'agent peut exécuter les deux premières étapes lorsque les permissions
l'autorisent, mais doit demander explicitement l'accord humain avant l'export.

## Règle de sécurité

Le niveau de risque vient du `Tool Registry`, jamais du JSON produit par le LLM.
Un modèle ne peut donc pas déclarer une opération destructive comme `read`.
