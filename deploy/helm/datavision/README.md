# DataVision AI — Helm chart v2.58.0

Ce chart déploie l'API, le worker, le frontend, le sandbox isolé et l'OpenTelemetry Collector. PostgreSQL, Redis, ClamAV et Vault sont volontairement référencés comme services externes afin de permettre un déploiement on-prem haute disponibilité conforme aux standards de l'organisation.

Avant un déploiement réel, remplacez toutes les valeurs `CHANGE_ME`, configurez `config.databaseUrl`, `config.redisUrl`, `config.clamavHost` et, pour le KMS externe, `config.vaultAddr` + `secrets.vaultToken`. Le chart conserve le mode Docker Compose : Kubernetes est optionnel.

Exemple :

```bash
helm upgrade --install datavision ./deploy/helm/datavision -f values.production.yaml -n datavision --create-namespace
```

### Secrets et stockage partagés

- Pour un cluster de production, `secrets.existingSecret` permet de référencer un Secret Kubernetes déjà géré par External Secrets, Vault ou l'opérateur de votre choix. Dans ce cas, positionnez `secrets.create=false`.
- Le PVC utilise `persistence.accessModes`; la valeur par défaut est `ReadWriteMany` afin de supporter les réplicas API/worker sur plusieurs nœuds. Le StorageClass choisi doit fournir RWX. Pour un stockage RWO, utilisez un seul consommateur par volume ou adaptez le chart à votre CSI.
