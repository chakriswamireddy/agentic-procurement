COMPOSE := docker compose -f infrastructure/docker-compose.yml

.PHONY: up up-app down reset seed check test test-backend test-frontend eval baseline verify api logs frontend-dev frontend-build

up:
	$(COMPOSE) up -d

up-app:
	$(COMPOSE) --profile app up -d --build

down:
	$(COMPOSE) down

reset:
	./scripts/reset_environment.sh --yes

seed:
	uv run python scripts/generate_dataset.py
	uv run python scripts/seed_postgres.py
	uv run python scripts/seed_mongodb.py
	uv run python scripts/ingest_documents.py

check:
	uv run python scripts/check_connectivity.py

test: test-backend test-frontend

test-backend:
	uv run ruff check .
	uv run pytest -q

test-frontend:
	cd frontend && npm test && npm run build

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

eval:
	uv run python scripts/evaluate_retrieval.py

baseline:
	uv run python scripts/measure_baseline.py

verify:
	bash scripts/verify_stack.sh

api:
	uv run uvicorn app.main:app --app-dir backend --reload --port 8000

logs:
	$(COMPOSE) logs -f
