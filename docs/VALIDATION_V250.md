# Validation — v2.5.0

## Backend

```text
pytest -q
37 passed
```

Les nouveaux tests vérifient :

- configuration automatique des watches sur métrique certifiée ;
- détection d'un changement important ;
- persistance dans l'Inbox ;
- preuve et investigations proposées ;
- déduplication lors d'un second scan identique ;
- changement de statut open → acknowledged ;
- filtrage de l'Inbox par statut.

## Compilation / syntaxe

```text
Python py_compile proactive_intelligence.py : OK
Python compileall                         : OK
page.tsx transpilation TypeScript         : OK
api.ts transpilation TypeScript           : OK
CSS braces                                : OK
```

Le build Docker/Next complet doit être confirmé dans l'environnement Docker cible.
