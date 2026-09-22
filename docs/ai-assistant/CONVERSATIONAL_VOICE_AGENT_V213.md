# DataVision v2.13 — Conversational & Voice Agent

## 1. Positionnement

L'AI Analyst devient une couche transversale permanente de DataVision.

```text
Utilisateur
   │
   ├── texte
   ├── voix
   ├── fichier
   └── sélection UI
          │
          ▼
┌──────────────────────────────┐
│ DataVision Agent Interface   │
│ floating + text + voice      │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Context / Observation Layer  │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Existing Agent Orchestrator  │
└───────┬───────────┬──────────┘
        │           │
        ▼           ▼
     Tools       Critic
        │
        ▼
 Data / Stats / ML / GIS / Reports
```

## 2. États UI du bouton flottant

```text
idle
listening
thinking
acting
speaking
warning
error
```

## 3. Modes vocaux

### Push-to-talk
Par défaut. L'utilisateur déclenche explicitement l'écoute.

### Conversation continue
Option activée explicitement. Le microphone redémarre après chaque tour de parole.

### Alertes vocales proactives
Configurables :

```text
off
critical_only
important
active
```

Les alertes critiques peuvent être lues à voix haute uniquement lorsque l'utilisateur a autorisé ce comportement.

## 4. Barge-in

Quand l'utilisateur recommence à parler :

1. arrêter immédiatement le TTS ;
2. annuler la lecture restante ;
3. écouter le nouvel énoncé ;
4. transmettre le nouvel intent à l'orchestrateur.

## 5. Observation de l'utilisateur

Ne pas faire de capture écran permanente.

Utiliser des événements structurés :

```text
workspace.opened
dataset.loaded
dataset.selected
dataset.quality.issue
column.selected
transform.previewed
transform.applied
chart.created
chart.error
analysis.started
analysis.failed
ml.training.started
ml.leakage.detected
model.evaluated
report.generated
file.uploaded
```

## 6. Contexte minimal d'un tour

```json
{
  "workspaceId": "ws_123",
  "route": "/model",
  "screen": "AutoML",
  "activeDatasetId": "ds_456",
  "activeModelId": "model_789",
  "selectedEntity": {
    "type": "column",
    "id": "income",
    "label": "income"
  },
  "recentEvents": []
}
```

## 7. Intervention proactive

Le moteur de règles doit distinguer :

```text
info
suggestion
warning
critical
```

Exemples :

- 3 % de valeurs manquantes → suggestion discrète ;
- type de colonne incompatible → warning ;
- fuite de données → critical ;
- suppression de 40 % des lignes → critical + confirmation.

## 8. Matrice d'autonomie

| Action | Exécution |
|---|---|
| Lire contexte | automatique |
| Profiling | automatique |
| Créer visualisation non destructive | automatique ou préférence utilisateur |
| Proposer nettoyage | automatique |
| Appliquer transformation réversible | configurable |
| Supprimer données/colonnes | confirmation |
| Écraser version | interdit par design |
| Écrire dans système externe | confirmation/policy |
| Envoyer message via connecteur | policy existante |
| Export contenant données sensibles | policy + confirmation |

## 9. Fichiers

Entrée :

```text
CSV, XLSX, JSON, Parquet, PDF, image,
GeoJSON, Shapefile/ZIP, GeoTIFF...
```

Sortie via moteurs DataVision :

```text
CSV, XLSX, PDF, DOCX, PPTX, HTML,
PNG/SVG, JSON, GeoJSON...
```

L'agent ne doit pas réimplémenter les moteurs d'export ; il les appelle comme outils.

## 10. Mémoire

Trois niveaux :

```text
Turn context
Session context
Workspace memory
```

La mémoire durable ne doit pas devenir une copie non gouvernée des données.

## 11. Confidentialité

L'assistant doit afficher clairement :

- microphone actif ;
- conversation continue active ;
- provider IA actif lorsque pertinent ;
- transfert externe de données lorsque configuré.

## 12. Critères v2.13

La version n'est "Done" que si :

- le bouton est disponible sur tous les écrans authentifiés ;
- texte et voix convergent vers le même orchestrateur ;
- les alertes proactives reposent sur le bus d'événements ;
- le TTS peut être interrompu ;
- le micro n'est jamais activé silencieusement ;
- l'agent reçoit le dataset/objet sélectionné ;
- les actions sensibles sont bloquées avant confirmation ;
- les événements et actions sont auditables ;
- les tests frontend/backend passent ;
- Docker passe.
