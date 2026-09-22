# Guide utilisateur - DataVision AI v2.81.6

## 1. Accès à DataVision
DataVision v2.81.6 demande une authentification par défaut. L'écran de connexion est donc normal et attendu.

### Première utilisation
Si aucun propriétaire n'existe encore, DataVision affiche automatiquement l'assistant de première configuration. L'utilisateur renseigne uniquement son nom, son email, son organisation, son mot de passe et sa confirmation. Aucun `BOOTSTRAP_SECRET` n'est demandé dans l'interface.

Même pendant cette première configuration, le lien **Vous avez déjà un compte ? Se connecter** permet d'ouvrir immédiatement le formulaire de connexion. Il est donc possible d'utiliser un compte déjà présent (notamment le compte test local) sans terminer d'abord la création du propriétaire.

Après cette première configuration :
1. le compte propriétaire est créé et la session est ouverte ;
2. sélectionnez le workspace ;
3. créez les utilisateurs/membres nécessaires ;
4. attribuez le rôle minimal adapté à chacun ;
5. activez MFA/WebAuthn selon la politique de l'organisation.

Les champs de mot de passe proposent une **icône œil** permettant d’afficher ou masquer temporairement la valeur saisie. Cette action ne modifie pas le mot de passe et reste locale au navigateur.

### Compte test en développement
Sur l’installation locale de développement fournie avec la release, un compte de démonstration est activé par défaut et créé automatiquement s’il n’existe pas :
- email : `demo@datavision.local` ;
- mot de passe : `DataVision8!` ;
- rôle : `admin` dans un workspace de démonstration isolé.

L’écran d’authentification affiche alors un bouton **Se connecter avec le compte test**. Ce compte sert uniquement aux essais et à la démonstration ; DataVision refuse de le provisionner lorsque `APP_ENV=production`. Le compte test n’empêche pas de créer ensuite le véritable compte propriétaire.

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

## Connexion et inscription

L’écran d’authentification propose deux modes standard : **Connexion** et **Inscription**. Un utilisateur peut passer de l’un à l’autre directement depuis les onglets ou les liens sous le formulaire. **Gouvernance & sécurité ne contient plus de second formulaire de connexion** : toutes les vues réutilisent la même session DataVision. Lorsque l’inscription est autorisée, la création d’un compte crée également une organisation et un workspace principal isolés. L’administrateur peut désactiver l’inscription libre avec `SELF_REGISTRATION_ENABLED=false` sans empêcher les comptes existants de se connecter.
