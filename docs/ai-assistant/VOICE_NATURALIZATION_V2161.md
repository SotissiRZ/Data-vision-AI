# DataVision v2.16.1 — Naturalisation de la voix

## Problème

Une copie UI comme :

```text
3 étape(s) exécutée(s) et validée(s)
```

était correcte visuellement mais mauvaise pour un système TTS, qui prononçait
littéralement les parenthèses.

## Correction

Le backend produit maintenant une phrase grammaticalement complète selon le
nombre.

Le frontend passe tout texte vocal dans `toSpeechText()` avant
`speechSynthesis`.

Le sanitizer :
- supprime `(s)`, `(e)`, `(es)` ;
- nettoie le Markdown ;
- remplace les longues URLs par une formulation naturelle ;
- humanise certains séparateurs comme `→` ;
- normalise la ponctuation et les espaces.

Le contrôleur vocal garde également un nettoyage de dernier recours.
