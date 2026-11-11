#!/usr/bin/env bash
# Phase 7: Demo Environment Preparation Script
# Prepares PostgreSQL, MongoDB, Qdrant, Redis, and seeded workflows for live demonstration.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" != "--yes" ]]; then
  echo "Usage: $0 --yes"
  echo "This script will reset and seed demo data in PostgreSQL, MongoDB, and Qdrant."
  exit 1
fi

echo "=========================================================="
echo "🛡️  AGENTIC PROCUREMENT: PREPARING DEMO ENVIRONMENT"
echo "=========================================================="

cd "$ROOT"

# 1. Reset database tables and collections
echo "Step 1/5: Resetting database states..."
bash "$ROOT/scripts/reset_environment.sh" --yes

# 2. Seed relational records (PostgreSQL)
echo "Step 2/5: Seeding PostgreSQL products, suppliers, and quotations..."
uv run python "$ROOT/scripts/seed_postgres.py"

# 3. Seed document profiles (MongoDB)
echo "Step 3/5: Seeding MongoDB supplier compliance documents & certifications..."
uv run python "$ROOT/scripts/seed_mongodb.py"

# 4. Ingest policy corpus into Qdrant
echo "Step 4/5: Ingesting policy documents into Qdrant vector index..."
uv run python "$ROOT/scripts/ingest_documents.py"

# 5. Seed demo user credentials
echo "Step 5/5: Hashing and seeding demo authentication credentials..."
uv run python "$ROOT/scripts/seed_user_credentials.py"

echo ""
echo "=========================================================="
echo "✨ DEMO ENVIRONMENT READY FOR 5-MINUTE WALKTHROUGH"
echo "=========================================================="
cat << 'EOF'
Demo Accounts (Standard Local Password: Password123!):
  - Requester: requester@example.com (USR0090) or user0002@example.test
  - Approver:  approver@example.com  (USR0091) or user0014@example.test
  - Auditor:   auditor@example.com   (USR0093) or user0015@example.test
  - Admin:     admin@example.com     (USR0092) or user0001@example.test

Key Demo Scenarios:
  1. Standard Conclusive Order:
     - Product: PRD0001 (Business Laptop 15")
     - Quantity: 50 units (under max order limit)
     - Max Delivery: 14 days
     - Required Certs: ISO-9001
     - Outcome: Eligible suppliers found, conclusive policy citations retrieved, pauses at approval.

  2. Ineligible / Excluded Scenario:
     - Product: PRD0001
     - Quantity: 50,000 units (exceeds all catalog suppliers' available inventory)
     - Outcome: LangGraph logs candidate exclusion reasons (INSUFFICIENT_QUANTITY), marks status failed/inconclusive.

  3. POL-002 Self-Approval Enforcement:
     - Requester submits request -> attempts approval -> HTTP 403 Forbidden.
     - Approver logs in -> reviews versioned recommendation -> approves -> MCP order created.

Services Checklist:
  - Frontend SPA: http://localhost:5173 (or port 80 in container)
  - Backend API:  http://localhost:8000
  - API Docs:     http://localhost:8000/docs
==========================================================
EOF
