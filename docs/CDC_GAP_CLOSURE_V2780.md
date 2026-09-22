# DataVision AI v2.78 — CDC Gap Closure

La v2.78 ferme les gaps internes encore automatisables sans transformer des hypothèses en preuves de production.

## Plans produit et quotas

Le catalogue `Starter / Pro / Entreprise` est exécutoire au runtime. Le plan est affecté au niveau organisation et les quotas sont appliqués aux workspaces, membres, datasets, connecteurs, notebooks, jobs et tours Assistant. Les capacités Enterprise sensibles (SSO/SCIM, actions gouvernées, Model Gateway externe) sont contrôlées par entitlement.

Le plan par défaut reste `entreprise` pour préserver la compatibilité des installations existantes. Un déploiement commercial peut définir `DEFAULT_PRODUCT_PLAN` explicitement.

## KMS cloud natif

Le Secret Vault supporte désormais AWS KMS, Google Cloud KMS et Azure Key Vault. DataVision chiffre la valeur avec une DEK AES-256-GCM aléatoire puis demande au KMS externe d'envelopper uniquement la DEK. L'AAD DataVision reste liée à l'enveloppe et le matériel de clé maître n'entre jamais dans DataVision.

Les identifiants cloud utilisent les chaînes d'identité natives des SDK (IAM/Workload Identity/Managed Identity selon le provider). Le mode Vault Transit existant reste disponible.

## Causalité : estimation, pas sur-promesse

L'endpoint ATE v1 fournit une estimation observationnelle par propensity score/IPW, diagnostics de recouvrement, balance et intervalle bootstrap. Il impose un traitement binaire et des covariables explicites. Le résultat contient toujours `causal_claim_allowed=false`: cette fonction n'autorise pas à transformer une association observationnelle en preuve causale expérimentale.

## Proactivité gouvernée

Les scans proactifs possèdent maintenant un planning persistant par dataset. Le worker réclame les échéances par mise à jour conditionnelle avant enqueue, afin d'éviter les doubles claims entre workers concurrents. Le statut de dernière exécution est persisté.

## Ce que cette release ne falsifie pas

Les §71 et §74 restent partiels tant que les preuves suivantes ne viennent pas d'un environnement réel : exécution de charge/capacité sur la cible, E2E de déploiement cible et UAT métier signée. Le §2 reste partiel car l'équivalence exhaustive avec tout l'écosystème externe R/Shiny/Jupyter n'est pas une propriété raisonnablement auto-certifiable par le produit.

La v2.78 prépare donc le hardening/Release Candidate avec une frontière claire entre **capacité implémentée** et **preuve externe encore à fournir**.
