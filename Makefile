.PHONY: help dev down build test lint format seed demo migrate logs shell clean

help:
	@echo "AP Reconciliation Orchestrator - Available Commands"
	@echo ""
	@echo "  make dev       - Start all services in development mode"
	@echo "  make down      - Stop all services"
	@echo "  make build     - Build Docker images"
	@echo "  make test      - Run all tests"
	@echo "  make lint      - Run linters"
	@echo "  make format    - Format code"
	@echo "  make seed      - Seed database with fixtures"
	@echo "  make demo      - Run end-to-end demo"
	@echo "  make migrate   - Run database migrations"
	@echo "  make logs      - Tail logs from all services"
	@echo "  make shell     - Open shell in API container"
	@echo "  make clean     - Remove all containers and volumes"

dev:
	cd infra && docker compose up -d
	@echo "Services starting..."
	@echo "  API:     http://localhost:8000"
	@echo "  Web:     http://localhost:3000"
	@echo "  Docs:    http://localhost:8000/docs"
	@echo ""
	@echo "Run 'make logs' to see output"

down:
	cd infra && docker compose down

build:
	cd infra && docker compose build

test:
	cd infra && docker compose exec api pytest -v --cov=apps/api

test-local:
	pytest apps/api/tests -v --cov=apps/api

lint:
	ruff check apps/api
	mypy apps/api

format:
	black apps/api
	ruff check apps/api --fix

seed:
	cd infra && docker compose exec api python scripts/seed.py

demo:
	cd infra && docker compose exec api python scripts/demo.py

migrate:
	cd infra && docker compose exec api alembic upgrade head

migrate-local:
	alembic upgrade head

logs:
	cd infra && docker compose logs -f

shell:
	cd infra && docker compose exec api bash

clean:
	cd infra && docker compose down -v --remove-orphans
	docker system prune -f

# Development helpers
install:
	pip install -e ".[dev]"

install-web:
	cd apps/web && pnpm install

dev-api:
	uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd apps/web && pnpm dev

dev-celery:
	celery -A apps.api.tasks.celery_app worker --loglevel=info
