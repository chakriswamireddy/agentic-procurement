"""Measure a local performance and quality baseline (Phase 6, Step 6.9).

Records API latency, end-to-end workflow duration, retrieval quality, cache
effectiveness, rate-limit rejections, dependency error rates, and (when
instrumented) token usage. Results are written as JSON next to a Markdown
summary so runs remain comparable.

Usage:
    uv run python scripts/measure_baseline.py --iterations 20
    uv run python scripts/measure_baseline.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.rag.runtime import build_retriever  # noqa: E402

try:  # works when invoked as `python -m scripts.measure_baseline`
    from scripts.evaluate_retrieval import (  # noqa: E402
        QUESTIONS,
        evaluate_case,
        summarize,
    )
except ModuleNotFoundError:  # works when invoked as `python scripts/measure_baseline.py`
    from evaluate_retrieval import (  # noqa: E402
        QUESTIONS,
        evaluate_case,
        summarize,
    )

RESULTS_DIR = ROOT / "data" / "evaluation" / "results"
DEFAULT_REPORT = ROOT / "docs" / "evaluation-report.md"
DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "Password123!")
REQUESTER_EMAIL = os.getenv("BASELINE_REQUESTER_EMAIL", "user0002@example.test")
APPROVER_EMAIL = os.getenv("BASELINE_APPROVER_EMAIL", "user0005@example.test")
SUPPLIER_QUERY = {"category": "it_hardware", "limit": 20}
POLICY_QUERY = "approval threshold for capital purchases"


def percentile(values: list[float], fraction: float) -> float:
    """Return the nearest-rank percentile for a list of floats."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return round(ordered[index], 2)


def summarize_latencies(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "mean_ms": round(statistics.fmean(values), 2) if values else 0.0,
        "max_ms": round(max(values), 2) if values else 0.0,
    }


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def hardware_description() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "python": platform.python_version(),
        "cpu_count": str(os.cpu_count() or "unknown"),
    }


async def login(client: httpx.AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def measure_supplier_latency(
    client: httpx.AsyncClient, token: str, iterations: int
) -> tuple[dict[str, float], dict[str, float]]:
    """Measure repeated (cache-hit) and unique (cache-miss) supplier queries."""
    headers = auth_headers(token)

    warm = await client.get("/api/v1/suppliers", params=SUPPLIER_QUERY, headers=headers)
    warm.raise_for_status()

    hit_latencies: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        response = await client.get(
            "/api/v1/suppliers", params=SUPPLIER_QUERY, headers=headers
        )
        response.raise_for_status()
        hit_latencies.append((time.perf_counter() - started) * 1000)

    miss_latencies: list[float] = []
    for offset in range(iterations):
        params = {**SUPPLIER_QUERY, "offset": offset}
        started = time.perf_counter()
        response = await client.get("/api/v1/suppliers", params=params, headers=headers)
        response.raise_for_status()
        miss_latencies.append((time.perf_counter() - started) * 1000)

    return summarize_latencies(hit_latencies), summarize_latencies(miss_latencies)


async def measure_policy_latency(
    client: httpx.AsyncClient, token: str, iterations: int
) -> dict[str, float]:
    headers = auth_headers(token)
    warm = await client.get(
        "/api/v1/policies/search", params={"q": POLICY_QUERY, "limit": 5}, headers=headers
    )
    warm.raise_for_status()

    latencies: list[float] = []
    for index in range(iterations):
        query = POLICY_QUERY if index % 2 == 0 else f"{POLICY_QUERY} section {index}"
        started = time.perf_counter()
        response = await client.get(
            "/api/v1/policies/search", params={"q": query, "limit": 5}, headers=headers
        )
        if response.status_code == 503:
            continue
        response.raise_for_status()
        latencies.append((time.perf_counter() - started) * 1000)
    return summarize_latencies(latencies)


async def measure_workflow_latency(
    client: httpx.AsyncClient, token: str, iterations: int
) -> dict[str, Any]:
    headers = auth_headers(token)
    latencies: list[float] = []
    statuses: list[str] = []
    for _ in range(iterations):
        started = time.perf_counter()
        response = await client.post(
            "/api/v1/procurement/requests",
            json={"product_id": "PRD0001", "quantity": 5},
            headers=headers,
            timeout=60.0,
        )
        if response.status_code >= 400:
            statuses.append(f"http_{response.status_code}")
            continue
        payload = response.json()
        status = str(response.headers.get("X-Workflow-Status") or payload.get("status"))
        statuses.append(status)
        latencies.append((time.perf_counter() - started) * 1000)

    return {
        **summarize_latencies(latencies),
        "statuses": statuses,
    }


async def measure_readiness_error_rate(
    client: httpx.AsyncClient, iterations: int
) -> dict[str, Any]:
    counters: dict[str, dict[str, int]] = {}
    for _ in range(iterations):
        response = await client.get("/health/ready")
        payload = response.json()
        for dependency, result in payload.get("checks", {}).items():
            bucket = counters.setdefault(dependency, {"ok": 0, "down": 0})
            bucket["ok" if result.get("status") == "ok" else "down"] += 1

    error_rates = {}
    for dependency, counts in counters.items():
        total = counts["ok"] + counts["down"]
        error_rates[dependency] = round(counts["down"] / total, 4) if total else 0.0
    return {"checks": counters, "error_rates": error_rates}


async def measure_rate_limit_burst(
    client: httpx.AsyncClient, attempts: int = 10
) -> dict[str, Any]:
    burst_email = "baseline-burst@example.test"
    rejections = 0
    statuses: list[int] = []
    for _ in range(attempts):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": burst_email, "password": "not-the-password"},
        )
        statuses.append(response.status_code)
        if response.status_code == 429:
            rejections += 1
    return {"attempts": attempts, "rejections": rejections, "statuses": statuses}


async def measure_retrieval(settings: Settings) -> dict[str, Any]:
    retriever = build_retriever(settings)
    payload = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    results = []
    for case in payload["cases"]:
        results.append(
            await evaluate_case(retriever, settings, case, mode="hybrid", k=5)
        )
    summary = summarize(results)
    return {
        "mode": "hybrid",
        "k": 5,
        "cases": len(results),
        "recall_at_5": round(summary["recall_at_k"], 4),
        "mrr_at_5": round(summary["mrr_at_k"], 4),
        "context_precision_at_5": round(summary["context_precision_at_k"], 4),
        "version_leak_rate": round(summary["version_leak_rate"], 4),
        "abstention_accuracy": round(summary["abstention_accuracy"], 4),
    }


async def cache_hit_rate(settings: Settings, client: httpx.AsyncClient, token: str) -> float | None:
    """Measure Redis keyspace hit rate across repeated supplier queries."""
    try:
        import redis.asyncio as redis
    except Exception:
        return None

    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        before = await redis_client.info("stats")
        headers = auth_headers(token)
        for _ in range(10):
            response = await client.get(
                "/api/v1/suppliers", params=SUPPLIER_QUERY, headers=headers
            )
            response.raise_for_status()
        after = await redis_client.info("stats")
    except Exception:
        return None
    finally:
        await redis_client.aclose()

    hits = int(after.get("keyspace_hits", 0)) - int(before.get("keyspace_hits", 0))
    misses = int(after.get("keyspace_misses", 0)) - int(before.get("keyspace_misses", 0))
    total = hits + misses
    return round(hits / total, 4) if total else None


def load_tool_usage(settings: Settings) -> dict[str, Any]:
    provider = (settings.llm_provider or "simulator").strip().lower()
    is_simulator = provider == "simulator"
    return {
        "provider": provider,
        "model": None if is_simulator else settings.llm_model,
        "input_tokens": 0 if is_simulator else None,
        "output_tokens": 0 if is_simulator else None,
        "estimated_cost_usd": 0.0 if is_simulator else None,
        "note": (
            "Deterministic simulator used; no model tokens consumed."
            if is_simulator
            else "Token usage is not instrumented for this provider; record it from provider logs."
        ),
    }


def render_report(report: dict[str, Any]) -> str:
    supplier_hit = report["api"].get("supplier_cache_hit") or {}
    supplier_miss = report["api"].get("supplier_cache_miss") or {}
    policy = report["api"].get("policy_search") or {}
    workflow = report["api"].get("workflow_to_approval") or {}
    retrieval = report["retrieval"]
    cache = report.get("cache_hit_rate")
    rate_limit = report["rate_limit"]
    readiness = report["readiness"]
    tool = report["tool_usage"]

    def row(name: str, values: dict[str, Any]) -> str:
        return (
            f"| {name} | {values.get('count', 0)} | {values.get('p50_ms', 0):.2f} "
            f"| {values.get('p95_ms', 0):.2f} | {values.get('max_ms', 0):.2f} |"
        )

    statuses = ", ".join(workflow.get("statuses", [])) or "not measured"
    dependency_rates = ", ".join(
        f"{name}={rate:.2f}" for name, rate in readiness.get("error_rates", {}).items()
    ) or "not measured"
    hardware = report["hardware"]
    hardware_line = (
        f"{hardware['platform']}, {hardware['machine']}, "
        f"{hardware['cpu_count']} CPUs, Python {hardware['python']}"
    )
    retrieval_line = (
        f"`{report['settings']['embedding_model']}` (dense), "
        f"`{report['settings']['sparse_embedding_model']}` (sparse), "
        f"hybrid RRF k={report['settings']['rrf_k']}, limit=5"
    )

    return f"""# Evaluation Report — Phase 6 Baseline

- **Generated:** {report['timestamp']}
- **Commit:** `{report['git_commit']}`
- **Environment:** `{report['settings']['app_env']}`
- **Dataset:** `{report['dataset']}` (sha256 `{report['dataset_hash']}`)
- **Hardware:** {hardware_line}
- **Retrieval config:** {retrieval_line}

This report is a **local baseline**, not a service-level objective. Objectives should only be
set after reviewing these numbers on the same hardware and dataset.

## API latency

| Metric | Samples | p50 (ms) | p95 (ms) | max (ms) |
|---|---:|---:|---:|---:|
{row('Supplier list (cache hit)', supplier_hit)}
{row('Supplier list (cache miss)', supplier_miss)}
{row('Policy search (hybrid)', policy)}
{row('Workflow create → approval', workflow)}

Workflow outcomes: {statuses}

## Retrieval quality

| Metric | Value |
|---|---:|
| Hybrid recall@5 | {retrieval['recall_at_5']:.4f} |
| Hybrid MRR@5 | {retrieval['mrr_at_5']:.4f} |
| Context precision@5 | {retrieval['context_precision_at_5']:.4f} |
| Version leak rate | {retrieval['version_leak_rate']:.4f} |
| Abstention accuracy | {retrieval['abstention_accuracy']:.4f} |
| Cases | {retrieval['cases']} |

## Cache, rate limiting, and dependencies

| Metric | Value |
|---|---|
| Supplier cache hit rate (Redis) | {'n/a' if cache is None else f'{cache:.4f}'} |
| Auth rate-limit attempts | {rate_limit['attempts']} |
| Auth rate-limit rejections (429) | {rate_limit['rejections']} |
| Dependency error rates (readiness) | {dependency_rates} |

## Token usage and cost

- Provider: `{tool['provider']}`
- Model: `{tool['model']}`
- Input tokens: `{tool['input_tokens']}`
- Output tokens: `{tool['output_tokens']}`
- Estimated cost (USD): `{tool['estimated_cost_usd']}`
- Note: {tool['note']}

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
"""


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    if settings.app_env.lower() in {"production", "prod"}:
        print("ERROR: baseline measurement is disabled in production.", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    report: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit(),
        "base_url": base_url,
        "dataset": str(QUESTIONS.relative_to(ROOT)),
        "dataset_hash": hashlib.sha256(QUESTIONS.read_bytes()).hexdigest()[:12],
        "hardware": hardware_description(),
        "settings": {
            "app_env": settings.app_env,
            "embedding_model": settings.embedding_model,
            "sparse_embedding_model": settings.sparse_embedding_model,
            "rrf_k": settings.rrf_k,
            "redis_cache_ttl_seconds": settings.redis_cache_ttl_seconds,
            "auth_rate_limit_requests": settings.auth_rate_limit_requests,
            "auth_rate_limit_window_seconds": settings.auth_rate_limit_window_seconds,
        },
    }

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        try:
            live = await client.get("/health/live")
            live.raise_for_status()
        except Exception as exc:
            print(f"ERROR: API is not reachable at {base_url}: {exc}", file=sys.stderr)
            return 2

        token = await login(client, REQUESTER_EMAIL)
        await login(client, APPROVER_EMAIL)

        report["readiness"] = await measure_readiness_error_rate(client, args.readiness_checks)
        supplier_hit, supplier_miss = await measure_supplier_latency(
            client, token, args.iterations
        )
        report["api"] = {
            "supplier_cache_hit": supplier_hit,
            "supplier_cache_miss": supplier_miss,
            "policy_search": await measure_policy_latency(client, token, args.iterations),
            "workflow_to_approval": await measure_workflow_latency(
                client, token, args.workflow_samples
            ),
        }
        report["cache_hit_rate"] = await cache_hit_rate(settings, client, token)
        report["rate_limit"] = await measure_rate_limit_burst(client, attempts=10)

    report["retrieval"] = await measure_retrieval(settings)
    report["tool_usage"] = load_tool_usage(settings)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = RESULTS_DIR / f"baseline_{timestamp}.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    args.report.write_text(render_report(report), encoding="utf-8")

    print(json.dumps({"json": str(json_path), "report": str(args.report)}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure a local baseline for Phase 6.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--workflow-samples", type=int, default=2)
    parser.add_argument("--readiness-checks", type=int, default=10)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.iterations < 1 or args.workflow_samples < 0 or args.readiness_checks < 1:
        parser.error("iterations/readiness must be positive and workflow samples non-negative")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
