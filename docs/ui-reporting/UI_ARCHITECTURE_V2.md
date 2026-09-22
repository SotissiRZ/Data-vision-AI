# DataVision AI — UI Architecture v2

## Objectif

Réduire la densité cognitive tout en conservant la profondeur analytique. La règle générale est : **progressive disclosure**.

## Shell

- topbar compacte, claire, avec le contexte du dataset ;
- sidebar sombre de 226 px contenant uniquement six espaces métier ;
- sous-navigation horizontale contextuelle ;
- canvas clair avec largeur utile maximale ;
- boutons primaires rares et cohérents ;
- détails techniques repliables ;
- indicateurs de provenance et confiance visibles sans monopoliser l'écran.

## Command Palette

`Ctrl/Cmd + K` ouvre une palette globale. Elle permet : navigation directe, recherche d'un module et envoi d'une question à AI Analyst.

## Goal Playbooks

La page d'accueil propose des entrées par objectif :

- comparer des groupes ;
- expliquer une variable cible ;
- prévoir une métrique ;
- analyser automatiquement.

Le système choisit ensuite le bon module ou l'orchestrateur, ce qui réduit la nécessité pour un utilisateur non expert de connaître le nom exact du test ou du modèle.

## Semantic Studio

Un écran dédié permet de gouverner les termes métier sans exposer à l'utilisateur les détails de stockage. La certification visuelle distingue une suggestion automatique d'une définition validée.

## Trust Center

Le Trust Center ne remplace pas la gouvernance enterprise. Il fournit un cockpit local de confiance : qualité, sémantique, reproductibilité, signaux de confidentialité, dataset/version et politiques de calcul.

## Decision Lab

La comparaison de scénarios utilise une vue dédiée : référence, scénarios, variation de la prédiction et sensibilité. Un avertissement permanent sépare prédiction et causalité.

## Anti-patterns explicitement évités

- sidebar de 20+ modules en permanence ;
- énormes bandeaux colorés dans chaque panneau ;
- chiffres importants cachés dans des tableaux ;
- tableaux très larges sans scroll interne ;
- assistant IA isolé sans accès au contexte ;
- résultats sans version du dataset ;
- effet « dashboard générique de template ».
