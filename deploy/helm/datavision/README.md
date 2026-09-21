# DataVision AI — Helm chart v2.60.0

Ce chart déploie l'API, le worker, le frontend, le sandbox isolé et l'OpenTelemetry Collector. PostgreSQL, Redis, ClamAV et Vault sont volontairement référencés comme services externes afin de permettre un déploiement on-prem haute disponibilité conforme aux standards de l'organisation.

Avant un déploiement réel, remplacez toutes les valeurs `CHANGE_ME`, configurez `config.databaseUrl`, `config.redisUrl`, `config.clamavHost` et, pour le KMS externe, `config.vaultAddr` + `secrets.vaultToken`. Le chart conserve le mode Docker Compose : Kubernetes est optionnel.

Exemple :

```bash
helm upgrade --install datavision ./deploy/helm/datavision -f values.production.yaml -n datavision --create-namespace
```

### Secrets et stockage partagés

- Pour un cluster de production, `secrets.existingSecret` permet de référencer un Secret Kubernetes déjà géré par External Secrets, Vault ou l'opérateur de votre choix. Dans ce cas, positionnez `secrets.create=false`.
- Le PVC utilise `persistence.accessModes`; la valeur par défaut est `ReadWriteMany` afin de supporter les réplicas API/worker sur plusieurs nœuds. Le StorageClass choisi doit fournir RWX. Pour un stockage RWO, utilisez un seul consommateur par volume ou adaptez le chart à votre CSI.

### Haute disponibilité v2.59

Le chart active par défaut les PDB, HPA et la répartition multi-nœuds pour les composants stateless. Le Job de migration s'exécute avant install/upgrade et le CronJob de sauvegarde produit des archives vérifiables dans le volume partagé. Ajustez les seuils HPA et les StorageClasses à la capacité réelle du cluster.


### Exploitation SRE v2.60

- `autoscaling.worker.mode=cpu` conserve le HPA historique ; `keda_redis` active le `ScaledObject` Redis si KEDA est installé dans le cluster.
- Les backups peuvent être copiés vers un stockage S3-compatible avec les paramètres `config.backupObjectStore*` et les credentials du Secret.
- `backup.restoreDrill` planifie un test de restauration non destructif séparé du CronJob de backup.
- `config.sreAutoAlertsEnabled=false` et `config.sreChaosEnabled=false` sont les valeurs de sécurité par défaut. Activez-les seulement après avoir configuré les destinations Governed Actions et un environnement de staging.
