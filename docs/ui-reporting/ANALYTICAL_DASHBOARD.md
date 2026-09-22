# DataVision AI — Analytical Dashboard v1.1

La page **Accueil** devient un tableau de bord analytique dès qu’un dataset est actif.

## Calculs affichés

Les chiffres et insights proviennent de moteurs déterministes : profilage pandas, règles de qualité, corrélations et moteur de recommandation de visualisations. Aucun LLM n'est utilisé pour calculer les métriques.

Le dashboard présente :

- lignes, variables, score qualité, cellules manquantes et doublons ;
- top des variables avec valeurs manquantes ;
- répartition des types de variables ;
- relations numériques les plus fortes, en excluant les identifiants probables ;
- distributions fortement asymétriques ;
- feed d'insights priorisés et actions proposées ;
- visualisations recommandées pour poursuivre l'analyse.

## Visualisations épinglées

Depuis **Visualization Studio**, le bouton **Ajouter au rapport** enregistre le payload analytique complet du graphique, avec la version du dataset qui l'a produit.

Le Report Builder peut inclure la section **Visualisations épinglées**. Les exports conservent le titre, le type, la version du dataset et un aperçu tabulaire des valeurs utilisées par le graphique. Les payloads complets restent conservés en JSON pour une évolution ultérieure vers un rendu graphique natif dans chaque format d'export.

## Traçabilité

Une visualisation épinglée est liée à :

- `dataset_id` ;
- `dataset_version` ;
- date de création ;
- configuration et données calculées du graphique.

Ainsi, un rapport ne mélange pas silencieusement des visualisations issues d'autres versions du dataset.
