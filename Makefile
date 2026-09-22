.PHONY: up down logs test typecheck build-web compose-check e2e-smoke e2e-production load-smoke production-acceptance production-signoff hygiene assistant-acceptance assistant-window-acceptance assistant-multimodal-acceptance typography-acceptance collaboration-acceptance governance-acceptance hardening-acceptance resilience-acceptance release verify-release

up:
	cp -n .env.example .env || true
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && pytest -q

typecheck:
	cd frontend && npm run typecheck

build-web:
	cd frontend && npm run build

compose-check:
	cp -n .env.example .env || true
	docker compose config -q

e2e-smoke:
	cd frontend && npm run test:e2e:smoke

e2e-production:
	cd frontend && npm run test:e2e:production

load-smoke:
	python scripts/load_smoke.py --url http://127.0.0.1:3005/api/health --requests 80 --concurrency 8

production-acceptance:
	python scripts/production_acceptance.py --root . --check

production-signoff:
	python scripts/production_signoff.py verify --evidence-dir production-evidence --require-all

hygiene:
	python scripts/repository_hygiene.py --check

assistant-acceptance:
	python scripts/assistant_acceptance.py --root . --check

assistant-window-acceptance:
	python scripts/assistant_window_acceptance.py --root . --check

assistant-context-acceptance:
	python scripts/assistant_context_acceptance.py --root . --check

assistant-multimodal-acceptance:
	python scripts/assistant_multimodal_acceptance.py --root . --check

typography-acceptance:
	python scripts/typography_acceptance.py --root . --check

collaboration-acceptance:
	python scripts/collaboration_acceptance.py --root . --check

governance-acceptance:
	python scripts/governance_acceptance.py --root . --check

entreprise-acceptance:
	python scripts/entreprise_acceptance.py --root . --check

hardening-acceptance:
	python scripts/hardening_acceptance.py --root . --check

resilience-acceptance:
	python scripts/resilience_acceptance.py --root . --check

distributed-ops-acceptance:
	python scripts/distributed_ops_acceptance.py --root . --check

regulatory-compliance-acceptance:
	python scripts/regulatory_compliance_acceptance.py --root . --check

release:
	python scripts/release.py --output dist

verify-release:
	python scripts/verify_release.py dist/datavision-ai-v$$(cat VERSION)-complet.zip --sha-file dist/datavision-ai-v$$(cat VERSION)-complet.zip.sha256
