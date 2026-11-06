# Phase 1 learning log

Date: 2026-11-02

## Scope implemented

- `app/core/config.py`: typed `pydantic-settings` settings loaded from the repository
  root `.env`, fail-fast validation, cached accessor, redacted `safe_dict()`/`repr`.
- `app/core/logging.py` and `middleware.py`: human-readable development logs, JSON
  logs outside development, request correlation IDs, one line per request.
- `app/core/errors.py`: `AppError` hierarchy plus handlers for app errors,
  `RequestValidationError`, `HTTPException`, and unexpected exceptions.
- `app/database/postgres/`: async engine created in lifespan, per-request session
  dependency with rollback on exception, SQLAlchemy table mappings.
- `app/database/mongodb/client.py`: one async Mongo client created in lifespan.
- `app/repositories/`: parameterized supplier SQL plus Mongo profile lookup.
- `app/services/supplier_service.py`: filter normalization, 404 decision, Postgres +
  Mongo composition, no FastAPI imports.
- `app/api/`: dependency wiring, supplier list/detail routes, liveness/readiness.
- `app/schemas/`: supplier, quotation, common error/health, and the Phase 2
  procurement request contract.
- Tests: 41 passing unit/API/integration tests with `pytest`, `pytest-asyncio`, and
  `httpx.ASGITransport`.

## Decisions and trade-offs

- **Dependencies use uv, not `requirements.txt`.** Runtime and dev dependencies live in
  `pyproject.toml` and `uv.lock`; run commands with `uv run`.
- **Money is serialized as a JSON string.** `Decimal` avoids binary float drift, and a
  string keeps clients from reintroducing float rounding.
- **Mongo degradation is graceful.** Supplier identity is authoritative in Postgres, so
  detail reads return core data plus `profile: null` and `X-Profile-Status: unavailable`
  when Mongo is down. We do not fail the whole detail request.
- **Readiness policy.** Postgres is required. MongoDB, Redis, and Qdrant are reported but
  optional for Phase 1 because later phases consume them. The response returns `503`
  only when a required dependency is down.
- **Transactions.** Repositories never commit. The request-scoped session rolls back on
  exception and closes deterministically; future write services own commit boundaries.
- **No `create_all`.** The schema remains owned by `scripts/sql/001_schema.sql`.
- **Connection failures map to `503`.** `asyncpg`/`SQLAlchemy` connection errors are
  translated to `dependency_unavailable` instead of leaking as `500`.

## Verification

```text
uv run ruff check .        -> All checks passed
uv run pytest -q           -> 41 passed
scripts/check_connectivity -> postgres 100 suppliers, mongo 100 profiles,
                              redis pong, qdrant 1 collection
```

Manual checks against `uvicorn app.main:app --app-dir backend`:

- `GET /docs` -> `200`
- `GET /health/live` -> `200 {"status":"ok"}`
- `GET /api/v1/suppliers?limit=3` -> `200`, total `100`
- `GET /api/v1/suppliers/SUP0001` -> `200` with Mongo profile and quotations
- `GET /api/v1/suppliers/SUP9999` -> `404` error envelope with correlation ID
- `GET /api/v1/suppliers?limit=0` -> `422` error envelope with field details
- `GET /health/ready` -> `200` with four component checks
- `X-Request-ID: test-123` -> echoed in the response and present in the request log

## Failure drills

1. **Postgres stopped**
   - `/health/live` -> `200`, as required for liveness.
   - `/health/ready` -> `503`, `checks.postgres.status = "down"`.
   - `/api/v1/suppliers` -> `503 dependency_unavailable` (not an unhandled `500`).
   - Restarting Postgres restored normal responses without restarting the API.
2. **MongoDB stopped**
   - `/api/v1/suppliers/SUP0001` -> `200`, core supplier fields and quotations present,
     `profile: null`, `X-Profile-Status: unavailable`.
3. **Invalid request IDs**
   - A 500-character `X-Request-ID` is replaced with a generated UUID instead of being
     logged raw.
4. **Invalid query input**
   - `limit=0`, `limit=101`, `offset=-1`, and `status=deleted` return `422` envelopes
     with field paths and messages.
5. **SQL injection attempt**
   - `q=' OR 1=1 --` returns `200` with zero matches; it is treated as literal text by a
     parameterized `ILIKE` query.

## Open follow-ups for later phases

- Redis and Qdrant remain readiness-only until their features are implemented.
- `requester_id` in `CreateProcurementRequest` is temporary and becomes JWT-derived in
  Phase 5.
- Caching and production pool tuning belong to Phase 6.
