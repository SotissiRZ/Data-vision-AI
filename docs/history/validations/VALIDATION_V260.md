# Validation v2.6.0

## Backend

```text
pytest -q
41 passed
```

Couverture fonctionnelle ajoutée :

- création d'une revue ;
- assignation reviewer/owner ;
- soumission ;
- approbation ;
- demande de corrections ;
- réouverture ;
- commentaires ;
- résolution de commentaires ;
- mentions et notifications ;
- restriction Viewer ;
- certification avec date d'expiration ;
- révocation de certification ;
- synthèse du Review Center.

## Syntaxe

```text
Python compileall      : OK
page.tsx transpilation : OK
api.ts transpilation   : OK
```

## Build frontend

Le build complet Next.js doit être confirmé dans Docker sur la machine cible. La transpilation syntaxique ne remplace pas un `next build` avec contrôle complet des types.
