# Validation v2.62.0

Périmètre : observabilité distribuée et opérations multi-cluster.

- contexte W3C `traceparent`, `X-Trace-ID` et `X-Request-ID` ;
- recherche de télémétrie par trace ;
- pipeline OpenTelemetry traces et export OTLP HTTP optionnel ;
- AlertmanagerConfig multi-canaux avec secrets externes ;
- vérification SHA-256 distante des réplications cross-region ;
- control plane multi-cluster ;
- bascule en deux phases avec jeton temporaire et préflight ;
- runbooks CLI exécutables.

Gate dédié : `DISTRIBUTED_OPS_ACCEPTANCE 8/8`.
