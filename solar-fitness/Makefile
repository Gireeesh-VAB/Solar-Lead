API_DIR := backend

.PHONY: up down migrate test run worker lint

up:
	docker compose -f backend/infra/docker-compose.yml up -d

down:
	docker compose -f backend/infra/docker-compose.yml down

migrate:
	cd $(API_DIR) && uv run alembic upgrade head

test:
	cd $(API_DIR) && uv run pytest

run:
	cd $(API_DIR) && uv run uvicorn solarfit.main:app --reload

worker:
	cd $(API_DIR) && uv run celery -A solarfit.workers.celery_app worker --loglevel=info

lint:
	cd $(API_DIR) && uv run ruff check .
