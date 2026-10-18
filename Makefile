.PHONY: up down logs migrate test seed
up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

migrate:
	docker compose run --rm api alembic upgrade head

test:
	cd services/api && pytest

seed:
	docker compose exec api python -m app.seed_demo
