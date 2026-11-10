# Phase 6 learning log — Redis, Observability, Evaluation, and Containerization

- **Date:** 2026-11-10
- **Scope completed:** Steps 6.0–6.13 (Redis caching ADR 0008, async Redis client lifecycle,
  supplier-search caching with TTL/jitter/version invalidation/fallback, Redis auth rate limiting
  with atomic window expiry and 429 Retry-After, structured workflow telemetry with correlation IDs
  and PII redaction, 20-case workflow evaluation dataset, evaluation harness with isolated invariants,
  RAGAS proxy evaluation with metadata, baseline performance/quality measurement, multi-stage non-root
  containerization, Docker Compose app profile integration, smoke verification, resilience outage tests,
  and deployment design ADR 0009)

## My explanation

Phase 6 hardens the system from a working prototype into an observable, measurable, resilient, and
containerized service ready for production-like operation. The guiding principle is evidence: every
cache is justified and safe to lose, every metric is measured against a documented baseline rather than
assumed, every outage is tested against a documented policy, and container builds are reproducible and
secure.

1. **Cache-aside with Versioned Invalidation:**
   Caching is applied strictly to idempotent, high-frequency supplier search queries. User authorization,
   JWTs, human approval state, and dynamic policy evidence are explicitly excluded. The cache key is
   composed of a cache version, normalized filters, and limit/offset: `suppliers:v{ver}:{hash}`. When
   supplier data changes (such as during re-seeding or catalog updates), invalidation is achieved in O(1)
   by incrementing `suppliers:cache_version`. Application code never uses the dangerous `KEYS` command.
   To prevent cache stampedes and synchronized expiries, a 60-second TTL is augmented with ±10% random
   jitter. If Redis fails, the system fails open: queries fall back transparently to PostgreSQL, logging a
   warning without interrupting user workflows.

2. **Account-Enumeration-Safe Rate Limiting:**
   The authentication endpoints (`/api/v1/auth/login` and `/api/v1/auth/token`) are protected by a
   distributed Redis rate limiter (5 attempts per 60-second window per client IP + SHA256(username)).
   Keys store hashed identifiers to avoid persisting raw PII. Rate limit rejection returns HTTP 429 with
   a generic message and a `Retry-After` header regardless of whether the submitted username exists in the
   database, strictly preventing timing and account enumeration attacks.

3. **Structured Telemetry and Context Propagation:**
   Telemetry captures node transitions, specialist latencies, retrieval chunk IDs, tool executions, and
   correlation IDs across the entire LangGraph lifecycle. All log records adhere to structured JSON
   standards with UTC ISO timestamps. A recursive scrubber redacts forbidden keys (passwords, tokens,
   secrets, PII, raw supplier rows) before emission.

4. **Multi-Layered Evaluation Framework:**
   Evaluation is partitioned into distinct layers:
   - Retrieval: Recall@k, MRR@k, and calibrated abstention against held-out policy queries.
   - Generation: Faithfulness and relevancy proxies recorded with embedding model and configuration metadata.
   - Workflow & Safety: A 20-case deterministic test harness asserting critical invariants (zero unapproved
     execution, self-approval blockage, stale version conflict, prompt injection isolation, tool timeout retries).

5. **Secure Multi-Stage Containerization:**
   The backend `Dockerfile` utilizes a two-stage build: a build stage compile/installs dependencies, while
   the runtime stage contains only the Python virtualenv and application source running as an unprivileged
   user (`app`, UID 10001). The container health check queries `/health/live` rather than readiness to avoid
   cascading container restarts when downstream backing stores temporarily flap.

## Architecture and execution flow

```text
  [ Client Request ] (HTTP / API)
        |
        +---> [ Auth Rate Limiter (Redis) ] ---> Allowed? (No: 429 Retry-After)
        |
  [ FastAPI Route Handler ] (with correlation_id & structured logging)
        |
        +---> [ Supplier Search: SupplierCache ]
        |       |-- Hit  --> Return cached DTO (schema validated)
        |       +-- Miss --> Query PostgreSQL -> Set Redis (TTL + jitter) -> Return
        |       +-- Fail --> Fallback to PostgreSQL (fail-open)
        |
  [ Specialist Orchestrator / LangGraph Workflow ]
        |
        |-- Telemetry: emits node start/end, duration_ms, retry_count, correlation_id
        |-- PII Redactor: scrubs passwords, tokens, auth headers from event payloads
        |
  [ Backing Services ]
        |-- PostgreSQL: Business state & LangGraph checkpoints
        |-- Redis: Caches & Rate limit buckets
        |-- Qdrant: Dense/sparse policy vectors
        |-- MongoDB: Supplier profiles & certifications
```

## What I implemented

- **6.0 Redis Usage Decision** (`docs/decisions/0008-redis-usage.md`):
  - Documented what is cached, key formulation, 60s TTL + jitter, version invalidation, and fail-open policy.
- **6.1 Async Redis Client** (`backend/app/database/redis/client.py`):
  - Global connection pool managed in application lifespan with short socket/connect timeouts.
- **6.2 Supplier-Search Cache** (`backend/app/database/redis/cache.py`, `backend/app/services/supplier_service.py`):
  - Cache-aside implementation with schema version checking, SHA256 key hashing, and database fallback.
- **6.3 Distributed Rate Limiting** (`backend/app/database/redis/rate_limit.py`, `backend/app/middleware/rate_limit.py`):
  - IP and username-hash bucket limiting with atomic expiration and `Retry-After` calculation.
- **6.4 Workflow Telemetry** (`backend/app/core/telemetry.py`):
  - Structured logging with correlation propagation and recursive PII redaction.
- **6.5 Workflow Evaluation Dataset** (`data/evaluation/workflow_cases.json`):
  - 20 deterministic cases covering comparison, policy retrieval, approval boundaries, safety, and timeouts.
- **6.6 Evaluation Harness** (`scripts/run_evaluation.py`):
  - Deterministic evaluation runner asserting status, evidence, execution invariants, and category summaries.
- **6.7 RAG Evaluation with Metadata** (`scripts/evaluate_rag.py`):
  - Evaluates context recall, precision, and faithfulness with configuration metadata.
- **6.8 Business-Rule and Safety Invariants** (covered in `run_evaluation.py` and `test_authorization.py`).
- **6.9 Baseline Measurement** (`scripts/measure_baseline.py`, `docs/evaluation-report.md`):
  - Measured p50/p95 latency for cache hits/misses, hybrid retrieval, and end-to-end workflow creation.
- **6.10 Multi-Stage Dockerfile** (`backend/Dockerfile`, `.dockerignore`, `requirements.txt`):
  - Non-root user, slim Python 3.12, no build tools in runtime layer, liveness health check.
- **6.11 Compose App Profile & Smoke Test** (`infrastructure/docker-compose.yml`, `scripts/verify_stack.sh`):
  - Added `backend` service with healthy dependencies, container DNS networking, and smoke script.
- **6.12 Failure and Resilience Tests** (`backend/tests/unit/test_resilience_outages.py`):
  - Tests covering Qdrant outage (503), corrupt cache rejection, and Postgres down (readiness 503).
- **6.13 Deployment Design** (`docs/decisions/0009-deployment-design.md`):
  - Documented Cloud Run API + worker, Cloud SQL, Atlas, Memorystore, Pub/Sub outbox, and security.

## Verification & Failure Drills

1. **Redis Down:** Supplier queries bypass cache and succeed via PostgreSQL; auth rate limiter logs a warning and fails open.
2. **Qdrant Down:** Policy retrieval raises `DependencyUnavailableError` (503); graph routes to inconclusive; approval cannot proceed.
3. **MongoDB Down:** Profile queries degrade; suppliers with missing certifications are treated as ineligible.
4. **PostgreSQL Down:** `/health/ready` returns 503 while `/health/live` returns 200; API stops accepting new writes.
5. **MCP Server Down:** Workflow halts before external execution; approval persists in PostgreSQL; retry safely replays with idempotency key.
6. **API Killed Mid-Workflow:** Restart API; graph checkpointer restores state from PostgreSQL checkpoint seamlessly.
7. **100 Login Attempts:** Requests 1–5 succeed; requests 6–100 return HTTP 429 with `Retry-After`; identical responses for existing/non-existing users.
8. **LangSmith Outage:** App continues running normally; tracing failures do not disrupt request processing.
9. **Corrupt Cache Payload:** Malformed JSON in Redis is caught, rejected, logged, and refetched from PostgreSQL.
10. **Eval Harness Repeatability:** Running `run_evaluation.py` across multiple runs produces identical 20/20 pass rates and deterministic timings.

## Checkpoint answers

1. **What is cached, under what key, for how long, and why is it safe to lose?**
   Supplier list search results are cached under `suppliers:v{version}:{sha256(filters)}` for 60 seconds (±10% jitter). It is safe to lose because the database is the authoritative source of truth; a miss simply falls back to PostgreSQL.
2. **How do you invalidate the cache without KEYS?**
   By incrementing the global `suppliers:cache_version` key in Redis. This changes the key prefix for all subsequent queries, causing old entries to expire naturally by TTL without scanning the keyspace.
3. **What happens to the API when Redis is down? Why did you choose fail-open or fail-closed for each use?**
   Supplier cache fails open (falls back to PostgreSQL) to preserve availability. Auth rate limiting fails open with a warning in development/demo to avoid locking out legitimate users, while production configurations can toggle fail-closed.
4. **How does rate limiting avoid leaking whether an account exists?**
   Rate limiting keys hash the IP and username together; the limiter decrements the quota and returns HTTP 429 before authentication logic checks user existence.
5. **What fields does a trace need to reconstruct one workflow?**
   `correlation_id`, `thread_id`, `request_id`, node name, start/end timestamps, duration_ms, retry attempt, outcome, error code, and tool execution references.
6. **Which data must never appear in logs or traces?**
   Raw passwords, JWT tokens, API keys, database credentials, full PII, and raw unredacted policy documents.
7. **Distinguish retrieval, generation, tool, workflow, business-rule, and safety evaluation. Give one metric for each.**
   - Retrieval: Recall@k.
   - Generation: Faithfulness.
   - Tool: Idempotent replay adherence.
   - Workflow: Checkpoint recovery success rate.
   - Business-rule: Supplier scoring ranking accuracy.
   - Safety: Self-approval rejection rate (100%).
8. **Why is a RAGAS score not proof of correctness?**
   RAGAS uses model-based or lexical heuristics that can suffer from judge bias, false positives on persuasive hallucinations, and insensitivity to domain policy nuances. It is an indicator, not ground truth.
9. **What does the Docker healthcheck test, and why liveness rather than readiness?**
   It tests `/health/live` (process responsiveness). Readiness checks external dependencies; using readiness for container health would cause Docker/orchestrators to kill and restart containers during transient dependency hiccups.
10. **What changes when services run in Compose versus on the host?**
    Hostnames resolve via Docker's internal DNS (`postgres`, `redis`, `mongodb`, `qdrant`) instead of `localhost`. Port mappings only expose selected external ports.
11. **Walk through one dependency outage and the expected user-visible behaviour.**
    If Qdrant is down, policy search returns `503 Service Unavailable`. In a workflow, policy research marks evidence as insufficient/inconclusive, preventing recommendation and approval.
12. **What would you change before deploying to Cloud Run, and what would force GKE or a queue?**
    Add secret injection from Secret Manager, configure a Serverless VPC connector, and externalize workflow resumption to Pub/Sub + async workers. Workflows that require long synchronous execution or WebSocket connections would force GKE or a task queue.
13. **How do you know an evaluation result is comparable to the previous run?**
    Results record the git commit hash, dataset SHA256, hardware profile, model/provider settings, and metric configurations.
14. **Which invariant is most important to test repeatedly, and why?**
    Zero unapproved execution. Procurement systems must never commit financial spend without validated, non-stale human authorization.

## Checkpoint score

- Self-assessment: **92/100** (Passing threshold: 75/100).
