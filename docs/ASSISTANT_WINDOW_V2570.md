# DataVision AI v2.57.0 — Fenêtre d'assistant dynamique

La fenêtre flottante de DataVision AI n'est plus figée. L'utilisateur peut désormais adapter l'espace de conversation à son écran et à la tâche en cours sans perdre le contexte de l'assistant.

## Comportement

- **Taille compacte** via le bouton `−`.
- **Taille normale** via le bouton `□`.
- **Taille agrandie** via le bouton `+`.
- **Redimensionnement manuel** en glissant la poignée `↖` située dans le coin supérieur gauche.
- La fenêtre reste ancrée en bas à droite ; l'agrandissement manuel se fait donc naturellement vers le haut et la gauche.
- Les dimensions sont bornées pour ne jamais dépasser l'espace visible.
- La taille choisie est mémorisée dans `localStorage` sous la clé `datavision.assistant.window.size`.
- Si le viewport change, les dimensions sont automatiquement recalées dans les limites disponibles.
- À faible largeur, l'en-tête se simplifie automatiquement grâce à une container query.
- Les animations de taille sont désactivées pendant le drag et lorsque `prefers-reduced-motion` est actif.

## Limites de référence

- minimum bureau : `340 × 420 px` ;
- maximum logique : `960 × 980 px`, toujours limité par le viewport ;
- preset compact : `390 × 560 px` ;
- preset normal : `500 × 760 px` ;
- preset agrandi : `760 × 860 px`.

## Validation

```bash
python scripts/assistant_window_acceptance.py --root . --check
```

Le gate attendu est `ASSISTANT_WINDOW_ACCEPTANCE 6/6`.
