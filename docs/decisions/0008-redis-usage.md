# ADR 0008: Redis Usage, Caching Strategy, Rate Limiting, and Invalidation

- **Status:** Accepted
- **Date:** 2026-11-07
- **Author:** Antigravity Agent
- **Context:** Phase 6 — Production, Observability, and Evaluation

---

## 1. Context and Problem Statement

The agentic procurement service relies on multiple data stores (PostgreSQL, MongoDB, Qdrant) and computational steps (embedding generation, vector retrieval, candidate filtering). To meet production availability, performance, and security goals, we require an in-memory coordination and caching layer. Redis is already provisioned in our local and production container stacks. 

We must define clear operational boundaries for Redis:
1. What data may be cached, under what keys, and with what lifetimes?
2. How is invalidation achieved without expensive full-keyspace operations?
3. How do we prevent cache stampedes and synchronized expirations?
4. What failure mode (fail-open vs. fail-closed) applies to each Redis use case?
5. What data is strictly prohibited from being cached?
6. How is rate limiting implemented and what PII safeguards exist?

---

## 2. Decision and Implementation Details

### 2.1 What Exactly Is Cached?
- **Supplier Search Results:** Normalized search queries containing pagination parameters (`limit`, `offset`) and filter dimensions (`categories`, `status`, `min_rating`). Supplier identities and core directory listings change infrequently (typically upon admin updates or seed runs).
- **Policy Hybrid Retrieval Results:** Policy search results for specific normalized queries, limits, and filter criteria (effective dates, classifications).

### 2.2 Cache Key Design
Cache keys must be deterministic, scoped, collision-resistant, and include versioning:

- **Supplier Search Key Structure:**
  ```text
  suppliers:v{cache_version}:{sha256(filter_tuple_json)}
  ```
  Where `cache_version` is retrieved from a master key `suppliers:cache_version` (integer, default `1`), and `filter_tuple_json` is the canonical JSON string of sorted search parameters:
  `{"categories": [...], "limit": 20, "min_rating": 4.0, "offset": 0, "status": "active"}`.

- **Rate Limiting Key Structure:**
  ```text
  ratelimit:{scope}:{identity_hash}:{window_epoch_minute}
  ```
  Where `identity_hash` is `sha256(f"{ip}:{identifier}".lower())`. Raw user emails or passwords are **never** stored in keys or values.

### 2.3 Time-To-Live (TTL) and Expiration Jitter
- **Supplier Search TTL:** Base TTL is **60 seconds**.
- **Jitter Mitigation:** Synchronized expiration (where many keys expire at the exact same second, causing downstream database spikes) is mitigated by adding a pseudo-random jitter of ±10% (i.e. 54s to 66s).
- **Rate Limit Window:** 60 seconds (aligned with fixed-window intervals).

### 2.4 Invalidation Strategy (No `KEYS` Scans)
- Calling `KEYS *` or pattern scanning in production blocks the Redis event loop, degrading latency for all tenants.
- **Versioned Keys Invalidation:** Invalidation is achieved by atomically incrementing the global version counter `INCR suppliers:cache_version`.
- Any subsequent search queries will immediately look up keys under `suppliers:v{new_version}:...`, causing an instant cache miss and repopulating under the new version.
- The previous version's keys are abandoned and safely reclaimed by Redis via their existing TTLs without requiring manual key deletion.
- Invalidation is triggered on:
  1. Completion of database seed scripts (`seed_postgres.py`).
  2. Supplier update/creation admin mutations.

### 2.5 Failure Modes: Fail-Open vs. Fail-Closed
- **Cache Reads and Writes (Fail-Open):**
  If Redis is unreachable, times out, or throws a connection error:
  - The cache operation logs a `WARNING` with the current `correlation_id`.
  - The request proceeds directly to the primary database (PostgreSQL/Qdrant).
  - The client receives a valid `200 OK` response without interruption.
  - Reason: A cache is an optimization, not a single point of failure for core business reads.

- **Authentication Rate Limiting (Configurable Policy):**
  - **In Development/Demo:** Fail-open with a high-priority warning log to prevent local developer lockouts during outages.
  - **In Production Deployment:** Fail-closed on auth attempts if Redis is persistently down, or fall back to an in-process local bucket with conservative limits to prevent brute-force attacks against Argon2 password verification.

### 2.6 What Must NEVER Be Cached
1. **User Passwords and Hashes:** Prohibited under all circumstances.
2. **Raw JWTs and Bearer Tokens:** Tokens are stateless and verified via HMAC signatures.
3. **User-Specific Authorization Decisions:** Access control and POL-002 approval rules must be evaluated dynamically against current state.
4. **Active Workflow Interrupt State:** Checkpointer state is persisted in PostgreSQL checkpointer storage; Redis does not store source-of-truth workflow state.
5. **Personally Identifiable Information (PII):** User emails, phone numbers, and physical addresses must never be cached in unhashed or unencrypted forms.

### 2.7 Why Redis Over In-Process (Local) Caching?
- **Horizontal Scalability:** The FastAPI backend is designed as a stateless container that can scale to multiple replicas behind a load balancer. An in-process cache would have low hit rates and inconsistent state across replicas.
- **Distributed Rate Limiting:** Brute-force protection requires a shared counter across all container instances.
- **Process Restarts:** Local cache is wiped on container restart, causing immediate stampedes against PostgreSQL on redeploys.

---

## 3. Consequences and Trade-offs

- **Memory Usage:** Redis memory usage is strictly bounded because all cached keys have finite TTLs.
- **Eventual Consistency:** During the 60-second window before natural TTL expiration (if an unversioned update occurs), reads might reflect slightly stale supplier metadata. Since supplier profiles change on human timescales, 60-second eventual consistency is well within operational tolerance.
- **Network Overhead:** Local Redis ping/round-trip latency is under 1 millisecond, which is orders of magnitude faster than PostgreSQL relational joins.
