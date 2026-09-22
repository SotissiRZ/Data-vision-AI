# DataVision AI v2.66 — Production Acceptance & E2E

## Objective

v2.66 turns the remaining P0 acceptance requirements into an executable sign-off process. It does **not** claim that a target environment has passed merely because the source contains CI definitions.

## Automated gates

- Frontend TypeScript and Next.js production build.
- Docker Compose configuration validation.
- Helm lint/render plus Conftest policy evaluation.
- Deployed Playwright smoke, MVP and production suites.
- Dependency-free HTTP load smoke with explicit p95/error-rate thresholds.
- Security workflow (dependency audit, Trivy and deployment policy).
- Production evidence records and final sign-off verifier.

## Target evidence model

A production sign-off requires seven evidence kinds: `ci`, `compose`, `helm`, `e2e`, `load`, `security`, and `uat`. Evidence is deliberately external to the source archive because CI success and business UAT cannot be truthfully inferred from code.

Record evidence with:

```bash
python scripts/production_signoff.py record --kind ci --status pass --source github-actions --details "CI run <id>"
```

Then verify the complete evidence bundle:

```bash
python scripts/production_signoff.py verify --evidence-dir production-evidence --require-all
```

## Windows / Docker Desktop

From the repository root:

```powershell
.\production-acceptance-windows.ps1
```

This runs Compose validation, a real image build/start, frontend typecheck/build, Playwright smoke/MVP/production tests and the local HTTP load smoke. It records local evidence but intentionally leaves CI, Helm, security and UAT to their authoritative environments.

## Definition of Done

The P0 automation is complete when `PRODUCTION_ACCEPTANCE` reports 8/8. The product-level DoD becomes fully signed only after `production_signoff.py verify --require-all` passes using real target evidence.
