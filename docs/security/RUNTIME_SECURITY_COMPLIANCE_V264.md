# DataVision AI v2.64 — Admission, runtime security & conformité continue

## Objectif

La v2.64 ajoute des contrôles de sécurité applicables avant déploiement, pendant l'exécution et après déploiement. Les politiques cluster-wide restent opt-in afin que le chart DataVision ne prenne jamais silencieusement le contrôle du cluster.

## Admission

Le chart peut livrer une `ClusterPolicy` Kyverno optionnelle. Elle impose le durcissement des Pods DataVision et peut vérifier les signatures Sigstore/Cosign des images publiées par la release. La vérification d'images est désactivée par défaut tant que le sujet keyless et les références d'images de l'organisation ne sont pas explicitement configurés.

## Runtime

Les deployments API, Web, Worker et Sandbox utilisent un contexte de sécurité durci : non-root, `RuntimeDefault` seccomp, `allowPrivilegeEscalation: false` et suppression des capabilities Linux. Les composants qui utilisent un root filesystem en lecture seule reçoivent des volumes temporaires dédiés pour leurs écritures nécessaires.

Un ConfigMap de règles Falco peut être livré pour détecter les shells interactifs, les écritures sous `/etc` et l'exécution de gestionnaires de paquets. Falco lui-même reste un composant de plateforme externe.

## Conformité continue

Le service `continuous_compliance` peut :

- capturer la posture déclarée ou une observation envoyée par un agent de cluster ;
- calculer la dérive par contrôle ;
- journaliser les événements runtime ;
- générer un evidence pack JSON avec SHA-256 ;
- exécuter périodiquement les scans via CronJob Kubernetes.

Les evidence packs distinguent la configuration déclarée des observations réelles. Une configuration seule n'est jamais présentée comme une preuve qu'un cluster externe applique effectivement une policy d'admission.

## Runbooks

```bash
python -m app.ops.compliance scan --all
python -m app.ops.compliance scan --workspace-id <workspace>
python -m app.ops.compliance evidence --workspace-id <workspace>
```
