# ADR 0009 — Deployment design

- **Status:** Proposed
- **Date:** 2026-11-10
- **Phase:** 6 (Step 6.13)
- **Context:** Local Compose stack works; this records what would change for a real
  deployment. It is a design, not an implemented production deployment.

## Decision

Target a managed-container deployment with **Cloud Run for the stateless API**, **Cloud SQL
for PostgreSQL**, **MongoDB Atlas**, **Memorystore for Redis**, and **Qdrant Cloud** (or
self-managed Qdrant on GKE). Run ingestion as a **Cloud Run Job**. Use an **async worker or
queue** for long-running workflow waits; do not hold a Cloud Run request open across a human
approval. Publish domain events through **Pub/Sub** with an **outbox** table.

```text
                    +-------------------+
  Client/UI  --->   |  Cloud Run API    |  stateless, JWT auth
                    |  (min 1 / max N)  |
                    +---------+---------+
                              | VPC connector
        +---------------------+----------------------+
        |                     |                      |
   Cloud SQL Postgres    Memorystore Redis     MongoDB Atlas
   (requests, checks,    (cache, rate limit)   (supplier profiles)
    LangGraph checkpoints)
                              |
                        Qdrant Cloud
                        (policy vectors)

  Pub/Sub topics: request.created, approval.recorded, execution.requested
  Cloud Run worker / Cloud Tasks: resumes workflows, executes with idempotency keys
  Outbox table + publisher job: reliable event publication
```

## Components

### API

- Cloud Run service, stateless container from `backend/Dockerfile`, non-root.
- Start with `min-instances=1`, `max-instances` bounded by database connection budget,
  concurrency 20–40, request timeout 60 s. The approval resume endpoint must finish well
  inside that; long execution is moved to a worker/queue.
- Secrets from Secret Manager (`JWT_SECRET`, provider keys, database passwords), mounted as
  env at runtime. Never bake secrets into images or commit env files.
- `APP_ENV=production` disables `/docs` and the development-only resume shortcut; readiness
  must require PostgreSQL, Redis, Qdrant, and Mongo per the chosen policy.
- A serverless VPC connector reaches private Cloud SQL, Memorystore, and Atlas peering.

### Data stores

| Store | Managed option | Notes |
|---|---|---|
| PostgreSQL | Cloud SQL for PostgreSQL | Business rows **and** LangGraph checkpoints in separate schemas/databases; point-in-time recovery; private IP. |
| MongoDB | MongoDB Atlas | Supplier profiles; least-privilege database user; no PII beyond synthetic data. |
| Redis | Memorystore for Redis | Cache and rate limiting; private IP; no persistence requirement for cache entries. |
| Qdrant | Qdrant Cloud or Qdrant on GKE | Named dense/sparse vectors; API key in Secret Manager; snapshot before re-index. |
| Object storage | Cloud Storage | Policy source documents and evaluation artifacts. |

### Long-running workflows

Cloud Run request-scoped execution is a poor fit for a workflow that pauses for human
approval. Options:

1. **Cloud Run API + async worker (chosen):** the API persists state and publishes
   `approval.recorded`; a worker resumes the graph from the Postgres checkpointer.
2. **GKE:** simplest mental model for long-lived workers, higher operational cost.
3. **Cloud Tasks / Pub/Sub push:** good for retryable execution, but each resume must still be
   idempotent and bounded.

The checkpoint is authoritative. A worker crash is recoverable by re-delivery; execution uses
`<request_id>:<recommendation_version>` as the idempotency key so replays create one ERP
purchase order.

### Ingestion

Run `scripts/ingest_documents.py` as a Cloud Run Job against a mounted/copied document bundle.
It is idempotent, records checksums, deletes stale points, and can `--rebuild` from source.

### Messaging and outbox

Write the business change and an `outbox` row in one PostgreSQL transaction. A publisher job
(or Debezium/CDC) forwards outbox rows to Pub/Sub. Consumers must tolerate duplicates.
Approval and execution events carry IDs only, never raw prices or tokens.

### Scaling

- API replicas are stateless; all shared state is in Postgres/Redis/Mongo/Qdrant.
- Size the SQL pool per instance: `instances × (pool_size + max_overflow)` must stay below the
  Cloud SQL connection limit, or put PgBouncer in front.
- Redis is not a source of truth: cache misses and outages must degrade to the database.
- Checkpointer connections are separate from application reads; budget them explicitly.

### Security

- Private networking only for data stores; no public database endpoints.
- Least-privilege service accounts per component (API, worker, ingestion job).
- Secret rotation via Secret Manager versions; no secrets in env files in production.
- JWT signing key rotation with overlap; tokens carry `sub/role/iss/aud/jti` only.
- Network policy denies egress except to approved dependencies and the ERP endpoint.
- Audit events are append-only and retained per policy.

### Observability

- Structured JSON logs with `correlation_id`, `thread_id`, `request_id`, node, outcome,
  retry count, and latency; PII redacted before emission (`app/core/telemetry.py`).
- OpenTelemetry spans across API → graph node → MCP tool; sample 1–10% in production.
- Cloud Monitoring alerts: 5xx rate, readiness failures by dependency, p95 workflow duration,
  workflows stuck in `resuming`, rate-limit rejection spikes, MCP tool errors.
- Dashboards: workflow funnel (received → awaiting approval → executed/rejected), cache hit
  rate, dependency error rates.

### Cost

- Model choice and token budget are the largest variable cost; explanations are capped and
  optional. Deterministic comparison and scoring never call a model.
- Supplier cache and rate limiting reduce database load; embedding batch size trades latency
  for throughput.
- Cloud Run scale-to-low with `min-instances=1` avoids cold-start surprises at the cost of one
  idle instance; GKE is only justified if worker count or networking grows.

## What changes before a real ERP

- Replace demo auth with OAuth/OIDC and enterprise identity; keep JWT claim discipline.
- Replace `ApprovalPolicyService` demo rules with a configurable policy engine and versioned
  rules; record policy version with each decision.
- Define the ERP idempotency contract, reconciliation job, and timeout/commit ambiguity
  handling (timeout after commit must not create a second order).
- PII classification, retention, and deletion for requester and supplier data; audit retention.
- Legal/compliance review for procurement thresholds, segregation of duties, and data residency.
- Load and chaos testing against managed services, not local Docker.

## Consequences

- The API stays stateless and horizontally scalable; approval waits move off the request path.
- More moving parts (worker, outbox, Pub/Sub) than the local stack, but each maps to a failure
  mode already tested locally (checkpoint resilience, idempotent execution, dependency outages).
- Cloud Run request limits force an explicit async design; that constraint is a feature, not a
  workaround, because human approval should never depend on a held HTTP connection.
