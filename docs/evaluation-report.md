# Evaluation Report — Phase 6 Baseline

- **Generated:** 2026-11-10T08:03:13.471141+00:00
- **Commit:** `a89e6b5071fda1bd3733e812844d2cd8d36c5385`
- **Environment:** `development`
- **Dataset:** `data/evaluation/rag_questions.json` (sha256 `dc871810f9d4`)
- **Hardware:** Linux-7.0.0-42-generic-x86_64-with-glibc2.43, x86_64, 16 CPUs, Python 3.12.15
- **Retrieval config:** `BAAI/bge-small-en-v1.5` (dense), `Qdrant/bm25` (sparse), hybrid RRF k=60, limit=5

This report is a **local baseline**, not a service-level objective. Objectives should only be
set after reviewing these numbers on the same hardware and dataset.

## API latency

| Metric | Samples | p50 (ms) | p95 (ms) | max (ms) |
|---|---:|---:|---:|---:|
| Supplier list (cache hit) | 5 | 10.14 | 13.43 | 13.43 |
| Supplier list (cache miss) | 5 | 8.32 | 9.40 | 9.40 |
| Policy search (hybrid) | 5 | 17.94 | 19.05 | 19.05 |
| Workflow create → approval | 2 | 66.58 | 73.81 | 73.81 |

Workflow outcomes: awaiting_approval, awaiting_approval

## Retrieval quality

| Metric | Value |
|---|---:|
| Hybrid recall@5 | 1.0000 |
| Hybrid MRR@5 | 0.8833 |
| Context precision@5 | 0.3222 |
| Version leak rate | 0.0000 |
| Abstention accuracy | 1.0000 |
| Cases | 20 |

## Cache, rate limiting, and dependencies

| Metric | Value |
|---|---|
| Supplier cache hit rate (Redis) | 1.0000 |
| Auth rate-limit attempts | 10 |
| Auth rate-limit rejections (429) | 5 |
| Dependency error rates (readiness) | postgres=0.00, mongodb=0.00, redis=0.00, qdrant=0.00 |

## Token usage and cost

- Provider: `simulator`
- Model: `None`
- Input tokens: `0`
- Output tokens: `0`
- Estimated cost (USD): `0.0`
- Note: Deterministic simulator used; no model tokens consumed.

## Interpretation

- Supplier reads are dominated by network + FastAPI overhead when Redis is warm; the unique
  offset sweep approximates cache-miss cost against PostgreSQL. The gap between the two rows is
  the measurable value of the cache on this host.
- Policy search includes hybrid embedding and Qdrant round-trips, so it is expected to be the
  slowest read path. Any p95 above ~1 s locally should be investigated before setting objectives.
- End-to-end workflow duration includes specialist research, validation, and persistence, not just
  HTTP overhead. It is the number to watch for regressions in Phases 6–7.
- Retrieval quality is unchanged from Phase 2 (`recall@5` near 1.0); this run confirms the
  evaluation pipeline still works after the Redis and observability changes.
- Rate-limit rejections should be `attempts - limit` when the limiter is enabled and Redis is
  healthy. Zero rejections means Redis was unavailable (fail-open) or limiting was disabled.

## Known limitations

- Single local host, Docker Desktop networking, and a synthetic 100-supplier dataset; absolute
  timings are not transferable to production.
- The workflow samples use the deterministic simulator, so LLM latency and token cost are absent.
- Readiness probes are cheap checks; dependency error rates measure probe failures, not full
  request failure rates under load.
- Redis keyspace hit rate is process-wide and includes keys outside the supplier cache. Use it as
  a directional signal, not an exact per-endpoint hit ratio.
- No sustained load test was run here. Phase 6 only asks for a load sanity check, recorded in the
  learning log.
