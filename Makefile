.PHONY: up down logs test typecheck build-web compose-check e2e-smoke hygiene assistant-acceptance assistant-multimodal-acceptance release verify-release

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

hygiene:
	python scripts/repository_hygiene.py --check

assistant-acceptance:
	python scripts/assistant_acceptance.py --root . --check

assistant-multimodal-acceptance:
	python scripts/assistant_multimodal_acceptance.py --root . --check

release:
	python scripts/release.py --output dist

verify-release:
	python scripts/verify_release.py dist/datavision-ai-v$$(cat VERSION)-complet.zip --sha-file dist/datavision-ai-v$$(cat VERSION)-complet.zip.sha256
