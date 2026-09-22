# Guide utilisateur - DataVision AI v2.81.0

## 1. Accès à DataVision
DataVision v2.81 demande une authentification par défaut. L'écran de connexion est donc normal et attendu.

### Première utilisation
Si aucun compte n'existe encore, l'administrateur réalise une initialisation unique du propriétaire. Selon la configuration, il doit fournir le `BOOTSTRAP_SECRET` généré lors de l'installation.

Après le bootstrap :
1. connectez-vous avec le compte propriétaire ;
2. sélectionnez le workspace ;
3. créez les utilisateurs/membres nécessaires ;
4. attribuez le rôle minimal adapté à chacun ;
5. activez MFA/WebAuthn selon la politique de l'organisation.

## 2. Rôles
Les fonctionnalités visibles dépendent du rôle :

- **Owner** : administration complète de l'organisation/workspace ;
- **Admin** : administration opérationnelle et gouvernance ;
- **Data Scientist** : données, analyses, modèles, notebooks ;
- **Analyst** : lecture, analyses, dashboards, reporting selon permissions ;
- **Viewer** : consultation et revue limitée.

Un rôle ne donne pas automatiquement accès à tous les datasets : l'appartenance au workspace et les politiques de données s'appliquent également.

## 3. Parcours utilisateur recommandé

### Étape 1 - Ajouter une source
Ouvrez **Sources** puis :
- importez un fichier ; ou
- configurez un connecteur autorisé ; ou
- sélectionnez une source object storage / CDC configurée par l'administrateur.

### Étape 2 - Examiner le dataset
Dans **Données**, sélectionnez le dataset et vérifiez :
- colonnes et types ;
- valeurs manquantes ;
- doublons ;
- distributions ;
- fraîcheur ;
- qualité/contrats.

### Étape 3 - Corriger la qualité
Le module Qualité peut proposer un plan de remédiation. Utilisez la prévisualisation avant/après puis confirmez uniquement les actions souhaitées. Les actions sensibles ne doivent pas être appliquées sans revue.

### Étape 4 - Préparer les données
Utilisez les transformations de préparation. Chaque opération crée une version traçable. Utilisez le lineage pour comprendre l'origine d'une version.

### Étape 5 - Explorer et analyser
Selon vos droits :
- statistiques ;
- SQL ;
- langage naturel/NLQ ;
- visualisations ;
- tableaux de bord ;
- analyses avancées.

### Étape 6 - Modéliser
Le module Modélisation supporte :
- classification ;
- régression ;
- clustering ;
- forecasting ;
- détection d'anomalies.

Utilisez les model cards, diagnostics, XAI et garde-fous Responsible AI avant toute décision importante.

### Étape 7 - Communiquer les résultats
Utilisez dashboards, storytelling et rapports. Les publications peuvent être soumises à des gates de fiabilité ou de validation selon la politique du workspace.

## 4. Assistant DataVision AI
Le bouton flottant ouvre l'assistant conversationnel. Il peut :
- utiliser le contexte du dataset/workspace actif ;
- expliquer une erreur ;
- proposer un workflow ;
- déclencher des actions autorisées ;
- manipuler/générer des artefacts selon les capacités disponibles.

L'assistant n'annule pas les règles de permission. Si une action est interdite à votre compte, l'assistant doit également la refuser.

## 5. Notebook Studio
Notebook Studio permet d'exécuter Python/R dans un environnement isolé. Vérifiez l'empreinte d'environnement affichée lorsque la reproductibilité est importante. Une modification de packages peut invalider le kernel et exiger son redémarrage.

## 6. Langues et accessibilité
L'interface supporte français, anglais, espagnol et arabe. L'arabe active le mode RTL. Les options d'accessibilité incluent navigation clavier, focus visible, contraste renforcé et réduction des animations.

## 7. Bonnes pratiques de sécurité utilisateur
- ne partagez jamais mot de passe, token ou secret de connecteur ;
- n'utilisez pas le même compte à plusieurs personnes ;
- activez MFA/WebAuthn quand disponible ;
- verrouillez votre poste lorsque vous vous absentez ;
- déconnectez toutes les sessions en cas de doute ;
- n'importez des données sensibles que dans le bon workspace ;
- vérifiez le destinataire avant publication/export ;
- signalez immédiatement une activité inhabituelle.

## 8. Problèmes courants

### « Authentification requise »
Reconnectez-vous et vérifiez que le workspace actif est correct. Si le problème persiste, contactez un administrateur.

### « Permission insuffisante »
Votre rôle ou le binding du dataset ne permet pas l'action demandée. Ne contournez pas le contrôle ; demandez une permission adaptée.

### Dataset absent
Vérifiez le workspace et les bindings de datasets.

### Notebook indisponible
Vérifiez l'état du sandbox et l'environnement du workspace.

### Connecteur en erreur
Vérifiez les credentials, le réseau, TLS et les permissions de la source. Ne collez jamais un secret dans un ticket non sécurisé.

## 9. Déconnexion
Utilisez **Déconnexion** à la fin d'une session. Pour un incident ou un appareil perdu, utilisez la révocation de sessions / « déconnexion de toutes les sessions ».
