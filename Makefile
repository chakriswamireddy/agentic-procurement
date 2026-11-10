COMPOSE := docker compose -f infrastructure/docker-compose.yml

.PHONY: up up-app down reset seed check test eval baseline verify api logs

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

test:
	uv run ruff check .
	uv run pytest -q

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
