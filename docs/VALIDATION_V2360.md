# Validation DataVision AI v2.36.0

## Scope

Context Engine v6 / Project Memory.

## Garanties fonctionnelles

- mémoire longue distincte de la mémoire de session ;
- stockage compact uniquement, sans transcript brut ni lignes de dataset ;
- isolation par scope local/workspace ;
- scope Enterprise dérivé du contexte authentifié ;
- recherche déterministe et rappel explicite ;
- rétention / limite / épinglage / oubli ;
- gestion de politique protégée par `workspace:manage` ;
- fallback : une panne de la mémoire projet ne bloque pas l'assistant.

## Validation exécutée

- Python compileall : OK
- tests backend : 254 passed
- tests v2.36 ciblés : 9 passed
- validation syntaxique TS/TSX modifié : OK

Le build Next.js complet et le build Docker ne sont pas revendiqués dans cet environnement.
