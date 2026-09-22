# DataVision v2.15.4 — correction de visibilité de l'assistant

## Cause

La base DataVision v2.12 ne contient ni Tailwind CSS ni configuration Tailwind.

Le composant assistant v2.15.3 utilisait encore des classes telles que :

```text
fixed
bottom-6
right-6
z-[100]
rounded-full
bg-slate-950
```

Ces classes n'avaient donc aucun effet dans la v2.12.

## Correction

Le composant utilise désormais :

```text
FloatingDataVisionAssistant.module.css
```

Le lanceur possède notamment :

```css
position: fixed;
right: 24px;
bottom: 24px;
z-index: 2147483002;
```

Le bouton visible porte `DV AI`.

Toutes les fonctionnalités précédentes sont conservées :
texte, voix, pièces jointes, contexte sémantique, alertes proactives,
plans, confirmations, reprise d'exécution et Model Gateway.
