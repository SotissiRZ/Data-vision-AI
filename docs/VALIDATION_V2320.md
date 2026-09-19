# Validation DataVision AI v2.32.0

## Scope

Context Engine v2: mémoire conversationnelle compacte persistante, résolution de relances et panneau de contexte visible.

## Invariants

- aucun transcript brut n'est persisté dans `assistant_session_memory` ;
- les références de colonnes sont invalidées quand le dataset actif change ;
- la mémoire d'un workspace n'est jamais chargée dans un autre workspace ;
- le contexte UI reste la source d'autorité pour le dataset/modèle/vue actifs ;
- une référence ambiguë continue de déclencher une clarification.
