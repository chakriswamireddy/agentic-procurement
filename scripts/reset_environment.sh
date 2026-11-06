#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/infrastructure/docker-compose.yml"
COMPOSE=(docker compose -f "$COMPOSE_FILE")

usage() {
    cat <<'EOF'
Usage: scripts/reset_environment.sh --yes

Destructive local reset:
  1. Stop containers.
  2. Remove all named Docker volumes for PostgreSQL, MongoDB, Redis, and Qdrant.
  3. Start the four stores and wait for health.
  4. Regenerate the deterministic dataset.
  5. Seed PostgreSQL and MongoDB.
  6. Rebuild the Qdrant policy index.
  7. Run the connectivity check.

All local store data is deleted. The required --yes flag confirms that you
understand this. Credentials and URLs are read from .env; they are never
hard-coded here.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

if [[ "${1:-}" != "--yes" ]]; then
    usage >&2
    echo "Refusing to reset without --yes." >&2
    exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
    echo "Missing $ROOT/.env. Copy .env.example and set local values first." >&2
    exit 1
fi

cd "$ROOT"

echo "Stopping containers and removing named volumes..."
"${COMPOSE[@]}" down --volumes --remove-orphans

echo "Starting containers and waiting for health..."
"${COMPOSE[@]}" up -d --wait --wait-timeout 120

echo "Regenerating dataset..."
uv run python scripts/generate_dataset.py

echo "Seeding PostgreSQL..."
uv run python scripts/seed_postgres.py

echo "Seeding MongoDB..."
uv run python scripts/seed_mongodb.py

echo "Rebuilding Qdrant policy index..."
uv run python scripts/ingest_documents.py

echo "Checking connectivity..."
uv run python scripts/check_connectivity.py

echo "Local environment reset complete."
