# ADR 0002: Data ownership and rebuild strategy

- **Status:** Accepted
- **Date:** 2026-10-31
- **Phase:** 0
- **Decision owner:** Data foundation

## Context

The platform uses PostgreSQL, MongoDB, Redis, Qdrant, and a workflow checkpointer. Each store must have a clear owner and a documented recovery path. Without this, it is easy to duplicate authoritative facts, lose audit records during a reset, or treat a rebuildable cache as a source of truth.

Named Docker volumes provide local persistence across container restarts and `docker compose down`. Only `docker compose down -v` or the reset script intentionally removes the data.

## Decision

| Data | System of record | Written by | Rebuildable from |
|---|---|---|---|
| Supplier identity/status | PostgreSQL | seed script / admin API | seed files |
| Quotations | PostgreSQL | seed script / admin API | seed files |
| Requests, recommendations, approvals, audit | PostgreSQL | application | not rebuildable; back up |
| Supplier profile extensions | MongoDB | seed script / integration | raw payloads + seed |
| Raw external payloads | MongoDB | integration | external source |
| Cache | Redis | application | always rebuildable |
| Policy document registry and ingestion status | PostgreSQL | ingestion service / script | policy documents |
| Policy index | Qdrant | ingestion service / script | policy documents |
| Graph checkpoints | LangGraph checkpointer | workflow | execution history |

## Ownership rules

- PostgreSQL is authoritative for supplier identity, supplier status, quotations, requests, recommendations, approvals, execution records, and audit events.
- MongoDB stores flexible supplier extensions and raw integration payloads. It must not become the authoritative source for supplier name, status, or category.
- Redis contains disposable cache and coordination data. Loss of Redis data must not lose a business decision.
- PostgreSQL owns the `policy_documents` registry: document metadata, checksum, chunk count, and ingestion status. It does not store full chunk text.
- Qdrant is a derived retrieval index. It can be deleted and rebuilt from `data/documents/` and the registry with `scripts/ingest_documents.py --recreate`.
- Graph checkpoints preserve workflow execution history. They may be needed to resume an in-flight workflow and are not reconstructed from the policy index.

## Persistence verification

The local stack uses named volumes: `pgdata`, `mongodata`, `redisdata`, and `qdrantdata`.

Expected checks after `docker compose restart` or `docker compose down` followed by `docker compose up -d`:

```bash
psql "$DATABASE_URL" -c "select count(*) from suppliers;"
mongosh --quiet "mongodb://localhost:27017/procurement" --eval 'db.supplier_profiles.countDocuments()'
redis-cli dbsize
curl -fsS http://localhost:6333/collections/policy_chunks
```

PostgreSQL, MongoDB, and Qdrant counts must survive because their data is written to named volumes. Redis may be empty because it is disposable cache.

## Consequences

- A local reset is intentionally destructive only through `scripts/reset_environment.sh --yes`, which removes named volumes and rebuilds all seed data.
- Backups are required for PostgreSQL business history and LangGraph checkpoints.
- Any component can be rebuilt independently when its source data and scripts are available.
