# Migration v2.46.0 → v2.47.0

Aucune migration destructive n'est requise. Les modèles sémantiques existants restent compatibles. Les nouveaux champs (`business_definition`, `allowed_roles`, glossaire lié) sont optionnels ; une liste `allowed_roles` vide signifie tous les rôles qui ont déjà accès au dataset. Le moteur interne conserve `semantic_version=2` et `semantic_query_engine_v2`.
