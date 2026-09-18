.PHONY: up down logs test
up:
	cp -n .env.example .env || true
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && pytest -q
