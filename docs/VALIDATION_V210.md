# Validation v2.10.0

- `pytest -q` : **55 passed**.
- `python -m compileall app` : OK.
- TypeScript/TSX syntax (`tsc --noEmit --noCheck`) : OK.
- `strictNullChecks=true`, `noImplicitAny=false` avec stubs React ciblés : OK.

Scénarios v2.10 couverts : création destination/règle, approval human-in-the-loop, signature HMAC, idempotency key, delivery audit, déduplication, quiet-hours scheduling, replay, RBAC et blocage de soumission directe d'un job `action_delivery`.

Le `next build` Docker complet n'est pas déclaré validé dans cet environnement. La validation finale doit être effectuée sur la machine Docker cible.
