# DataVision v2.13.1 — Agent Tooling, Activity & Memory

## But

La v2.13.0 fournit l'interface flottante, la voix et le bus de contexte.
La v2.13.1 ajoute la couche qui empêche l'agent d'être un simple chatbot :

```text
Observation → Détection → Plan → Tool Registry → Policy → RBAC/RLS → Exécution → Audit
```

## Tool Registry

Un outil n'est jamais une fonction Python arbitraire donnée au LLM.

Chaque outil possède un contrat :

```text
name
description
category
risk
required_permissions
requires_dataset
requires_model
deterministic
```

L'orchestrateur ne peut proposer que des outils enregistrés.

Exemples initiaux :

```text
profile_dataset
inspect_missing_values
inspect_data_leakage
diagnose_analysis_failure
diagnose_visualization
create_visualization
apply_reversible_transform
delete_column
generate_report
export_sensitive_data
send_external_message
```

Ces déclarations ne prétendent pas réimplémenter les moteurs DataVision.
Elles constituent le pont gouverné vers les fonctions existantes.

## Détection de blocage

L'agent ne doit pas espionner l'utilisateur au pixel près.

Il observe des événements sémantiques :

```text
analysis.failed
visualization.error
transform.failed
query.failed
ml.training.failed
*.retried
```

Si plusieurs erreurs identiques apparaissent dans une courte fenêtre, l'agent peut proposer :

> « Je vois que cette étape échoue plusieurs fois. Je peux diagnostiquer le problème. »

Aucune conclusion psychologique n'est déduite.

## Mémoire

La mémoire de session conserve uniquement un état compact :

```text
objectif
tâche courante
entités actives
faits utiles
décisions récentes
```

Elle n'est pas une copie intégrale des données ni une archive cachée de la conversation.

## Couche d'exécution

Avant exécution :

```text
1. outil enregistré ?
2. contexte requis disponible ?
3. action interdite ?
4. confirmation nécessaire ?
5. RBAC/RLS DataVision autorise ?
6. handler hôte réellement branché ?
7. exécution
8. audit
```

## Important

Le `AllowAllDevelopmentAuthorization` fourni dans ce patch est uniquement un
adaptateur de développement. Il ne doit pas être utilisé tel quel en production.

Le dépôt DataVision v2.12 possède déjà une boundary Entreprise RBAC/RLS/column
security ; la v2.13 doit s'y brancher au lieu de la dupliquer.
