# Phase 0 learning log — Environment and data foundation

- **Date:** 2026-11-02
- **Module / concept:** Local infrastructure, deterministic synthetic data, data ownership, idempotent seeding, minimal vector ingestion
- **Problem being solved:** Give the later application phases a reproducible local environment with trustworthy supplier, quotation, policy, and integration data.

## My explanation

The four stores have deliberately narrow jobs. PostgreSQL owns structured business
facts: supplier identity and status, products, quotations, requests, recommendations,
approvals, execution records, and audit events. MongoDB owns flexible supplier profile
extensions and raw external payloads. Redis is disposable cache and coordination data.
Qdrant is a derived retrieval index over policy text.

The seed data is synthetic and deterministic because tests must be repeatable. Every
quotation references an existing supplier and product, every profile links to a
PostgreSQL supplier ID, and the documented edge cases are injected by ID rather than
by chance.

## Architecture and execution flow

```text
generate_dataset.py
        |
        +--> data/seed/*.json,*.jsonl
        |          |
        |          +--> seed_postgres.py ---> PostgreSQL
        |          |
        |          +--> seed_mongodb.py ----> MongoDB
        |
data/documents/*.md
        |
        +--> ingest_documents.py -----------> fastembed ---> Qdrant

check_connectivity.py queries all four stores.
reset_environment.sh removes volumes, restarts the stack, and reruns the pipeline.
```

## What I implemented manually

- Docker Compose stack with healthchecks, one named network, and named volumes.
- `.env.example`, `.gitignore`, Makefile, and reproducible Python environment.
- Deterministic generator with fixed seed, fixed reference date, stable IDs, JSON
  sorting, `--check`, and `--seed`.
- PostgreSQL schema with text business IDs, foreign keys, checks, indexes, decimal
  money, and `TIMESTAMPTZ` timestamps.
- PostgreSQL and MongoDB seeders using upserts and validation.
- Twelve synthetic policy documents with active, obsolete, draft, near-miss, and
  prompt-injection fixtures.
- Qdrant ingestion with UUIDv5 point IDs, deterministic chunking, payload indexes, and
  dimension validation.
- Connectivity checker with secret redaction.
- Reset script and tests.

## What failed and what I changed

| Failure | Root cause | Fix |
|---|---|---|
| `pytest` could not collect tests | `Any` was used in `conftest.py` without `from typing import Any` | Added the import |
| Integration tests failed with `ImportError: cannot import name 'run_script'` | Tests referenced `run_script`, but conftest defined `_run_script` | Renamed the helper and updated fixtures |
| Ruff reported `F821 Undefined name 'Any'` | Same missing import as the pytest collection failure | Fixed with the import |

Verified after the fixes:

```text
uv run ruff check .
All checks passed!

uv run pytest -q
8 passed
```

## Failure drills

| # | Drill | Observed behaviour |
|---|---|---|
| 1 | Stop PostgreSQL and run the connectivity checker | `postgres: failed (connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused ...)`; other stores remained `ok`; exit code `1`; no credentials printed |
| 2 | Insert a quotation with supplier `SUP9999` | PostgreSQL rejected the row with constraint `quotations_supplier_id_fkey`; quotation count stayed `500` before and after |
| 3 | Run both seeders more than once | `0 inserted, N updated` on reruns; all record counts stayed unchanged |
| 4 | Run Qdrant ingestion twice | Point count stayed at `68` |
| 5 | Query obsolete policy chunks | Filter returned `4` chunks, all for `POL-011`; active-policy queries excluded `POL-011` |
| 6 | Remove `document_id` from a document's front matter | Ingestion rejected the file with `bad.md: missing front matter fields: document_id` |
| 7 | Run `make reset` (removes volumes and rebuilds) | Exit code `0`; regenerated 8 files; PostgreSQL seeded 15 users, 100 suppliers, 200 products, 500 quotations, 100 requests, 150 orders; MongoDB seeded 100 profiles and 60 raw payloads; Qdrant indexed 68 chunks; connectivity passed |
| 8 | Check ingestion against a 768-dimension collection | Rejected with `collection policy_chunks has vector size 384, expected 768; use --recreate or fix EMBEDDING_DIM` |
| 9 | Rebuild the collection with `ingest_documents.py --recreate` | Collection was deleted and rebuilt; ingestion reported `68` chunks and the collection count returned to `68` |

## Persistence verification

Counts before restart:

```text
postgres {'suppliers': 100, 'quotations': 500, 'users': 15}
mongodb profiles 100
mongodb raw_payloads 60
redis probe persists
qdrant points 68
```

The same values survived:

1. `docker compose restart`
2. `docker compose down` followed by `docker compose up -d --wait`

This confirms that the named volumes, not the container lifecycle, hold the data.
`docker compose down -v` and `make reset` are the only intentional destructive paths.

## Trade-offs

- The Phase 0 schema is idempotent SQL rather than a migration framework. This keeps
  the learning surface small; Phase 1 can replace it with migrations while keeping
  `001_schema.sql` as the canonical reference.
- The generator uses simple loops instead of Faker so edge-case IDs and deterministic
  output are easy to reason about.
- Qdrant chunking is intentionally minimal. Phase 2 replaces it with a better chunker
  and hybrid retrieval.
- Redis is treated as disposable. If a future feature needs durable coordination, it
  must not rely on Redis alone.
- The raw ERP payload fixture is small and synthetic. It tests shape and malformed
  records, not real integration volume.

## Questions I cannot answer yet

- Which retrieval strategy will best handle policy conflicts once hybrid search and
  reranking are added?
- What backup and restore policy is appropriate for the PostgreSQL business history
  and LangGraph checkpoints?
- How should supplier profile extensions be reconciled when an external ERP payload
  disagrees with PostgreSQL identity data?

## Checkpoint answers

1. **What does each store own?** PostgreSQL owns structured business records. MongoDB
   owns supplier profile extensions and raw payloads. Redis owns disposable cache.
   Qdrant owns the derived policy index. None of MongoDB, Redis, or Qdrant is
   authoritative for supplier identity, status, or transaction history.
2. **Why text supplier IDs?** They are stable business identifiers shared with external
   systems. They remain human-readable, avoid surrogate-key renumbering, and can be
   reused as MongoDB `_id` values and Qdrant payload references.
3. **Why `NUMERIC` for money?** Binary floating point cannot represent decimal
   fractions exactly. Repeated arithmetic can change comparisons and recommendation
   scores. `NUMERIC(12,2)` stores exact amounts with a fixed scale.
4. **What makes seeding idempotent?** Stable IDs plus `INSERT ... ON CONFLICT DO
   UPDATE`. Reruns repair missing or stale rows without creating duplicates, which
   makes reset and retry safe and keeps test counts stable.
5. **How is the Qdrant index rebuilt?** Delete the collection with `--recreate`, then
   run `scripts/ingest_documents.py`. The source of truth is `data/documents/*.md`;
   point IDs are UUIDv5 values over document, version, and chunk index.
6. **Restart versus `down -v`?** A restart keeps containers and named volumes. `down`
   removes containers and the network but keeps named volumes. `down -v` removes the
   volumes, so all store data is lost.
7. **Why not rely on `depends_on`?** It controls start order, not readiness. A service
   can be started but not accepting connections. Healthchecks decide when the service
   is actually ready, and `up --wait` uses that status.
8. **Which edge cases exist?** Expired quotations `QTN00011`, `QTN00123`,
   `QTN00245`, `QTN00351`, `QTN00489`; insufficient quantities `QTN00036`,
   `QTN00156`, `QTN00278`, `QTN00399`, `QTN00444`; long deliveries `QTN00066`,
   `QTN00178`, `QTN00299`, `QTN00356`, `QTN00471`; missing certifications
   `SUP0007`, `SUP0029`, `SUP0053`, `SUP0074`, `SUP0096`; inactive or suspended
   attractive suppliers `SUP0018`, `SUP0037`, `SUP0061`, `SUP0083`, `SUP0091`;
   duplicate-looking names `SUP0012` and `SUP0013`; anomalous price `QTN00312`.
   They feed eligibility, expiry, certification, anomaly, and data-quality tests.
9. **What is the risk of storing supplier name in both stores?** The copies can
   diverge, producing stale or contradictory values and unclear ownership. PostgreSQL
   must remain the single source of truth for identity; MongoDB should store only
   extensions.
10. **Why is a Redis TTL entry safe to lose?** The value is cache or coordination
    state that can be recomputed. Losing it costs latency, not a business decision or
    an audit record.

## Checkpoint score

**Self-assessed score: 82/100**

| Dimension | Score | Notes |
|---|---:|---|
| Conceptual understanding | 17/20 | Store responsibilities and deterministic data are clear; retrieval strategy is still Phase 2 work |
| Architecture and data flow | 13/15 | Rebuild paths are explicit; backup and restore are not implemented |
| Independent implementation | 21/25 | Full pipeline works; migration strategy is deferred |
| Debugging and trade-offs | 17/20 | Failure drills reproduced; external integration remains synthetic |
| Interview explanation | 14/20 | Core answers are solid; deeper retrieval and production design need practice |

This is above the Phase 0 threshold of 75. Remaining gaps are retrieval quality,
backup/restore, and real external integration.
