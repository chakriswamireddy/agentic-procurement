"""Bounded runner: retries, permanent failures, timeouts, deadlines (step 4.2)."""

import asyncio

from app.agents.contracts import PermanentError, TransientError
from app.agents.runner import SpecialistMetrics, compute_backoff, run_specialist


class FakeSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


async def test_retries_transient_then_succeeds() -> None:
    attempts = {"n": 0}

    async def operation() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TransientError("boom", code="flaky")
        return "ok"

    sleep = FakeSleep()
    result = await run_specialist(
        name="supplier_lookup",
        operation=operation,
        timeout_s=1.0,
        correlation_id="corr-1",
        max_attempts=3,
        base_delay_s=0.2,
        max_delay_s=2.0,
        sleep=sleep,
        rng=lambda: 0.5,
    )

    assert result.ok is True
    assert result.data == "ok"
    assert result.attempts == 3
    assert result.error is None
    # Full jitter at rng=0.5 is exactly the capped exponential delay: 0.2, 0.4.
    assert sleep.delays == [0.2, 0.4]


async def test_permanent_error_is_not_retried() -> None:
    calls = {"n": 0}
    sleep = FakeSleep()

    async def operation() -> str:
        calls["n"] += 1
        raise PermanentError("bad request", code="invalid_supplier_query")

    result = await run_specialist(
        name="supplier_lookup",
        operation=operation,
        timeout_s=1.0,
        correlation_id="corr-2",
        max_attempts=3,
        sleep=sleep,
    )

    assert result.ok is False
    assert result.attempts == 1
    assert calls["n"] == 1
    assert sleep.delays == []
    assert result.error is not None
    assert result.error.code == "invalid_supplier_query"
    assert result.error.transient is False


async def test_timeout_returns_timeout_code_within_budget() -> None:
    sleep = FakeSleep()

    async def operation() -> str:
        await asyncio.sleep(0.05)
        return "too slow"

    result = await run_specialist(
        name="supplier_lookup",
        operation=operation,
        timeout_s=0.01,
        correlation_id="corr-3",
        max_attempts=3,
        base_delay_s=0.001,
        timeout_code="supplier_timeout",
        sleep=sleep,
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "supplier_timeout"
    assert result.error.transient is True
    assert result.attempts == 3
    assert len(sleep.delays) == 2


async def test_deadline_stops_before_backoff_sleep() -> None:
    sleep = FakeSleep()

    async def operation() -> str:
        raise TransientError("always down", code="supplier_db_unavailable")

    result = await run_specialist(
        name="supplier_lookup",
        operation=operation,
        timeout_s=1.0,
        correlation_id="corr-4",
        max_attempts=3,
        base_delay_s=0.5,
        deadline_s=0.01,
        sleep=sleep,
    )

    assert result.ok is False
    assert result.attempts == 1
    assert sleep.delays == []


async def test_unexpected_exception_is_wrapped_and_not_retried() -> None:
    sleep = FakeSleep()

    async def operation() -> str:
        raise ValueError("kaboom")

    result = await run_specialist(
        name="policy_retrieval",
        operation=operation,
        timeout_s=1.0,
        correlation_id="corr-5",
        max_attempts=3,
        sleep=sleep,
    )

    assert result.ok is False
    assert result.attempts == 1
    assert sleep.delays == []
    assert result.error is not None
    assert result.error.code == "unexpected_specialist_error"
    assert result.error.transient is False
    # The wrapper message must not leak the original payload or stack trace.
    assert "kaboom" not in result.error.message
    assert result.error.details.get("cause") == "ValueError"


async def test_always_transient_operation_hits_attempt_cap() -> None:
    """Loop prevention: a repeated identical failure is retried at most 3 times."""
    calls = {"n": 0}
    sleep = FakeSleep()

    async def operation() -> str:
        calls["n"] += 1
        raise TransientError("outage", code="policy_index_unavailable")

    result = await run_specialist(
        name="policy_retrieval",
        operation=operation,
        timeout_s=1.0,
        correlation_id="corr-6",
        max_attempts=100,
        sleep=sleep,
    )

    assert result.ok is False
    assert calls["n"] == 3
    assert result.attempts == 3
    assert len(sleep.delays) == 2


async def test_metrics_count_calls_retries_and_failures() -> None:
    metrics = SpecialistMetrics()
    calls = {"n": 0}

    async def operation() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("flaky", code="flaky")
        return "ok"

    await run_specialist(
        name="supplier_lookup",
        operation=operation,
        timeout_s=1.0,
        correlation_id="corr-7",
        max_attempts=3,
        sleep=FakeSleep(),
        metrics=metrics,
    )

    summary = metrics.summary()
    assert summary["specialist_calls"] == 1
    assert summary["specialist_retries"] == 2
    assert summary["specialist_failures"] == 2


def test_backoff_is_capped_and_jittered() -> None:
    assert compute_backoff(attempt=1, base_delay_s=0.2, max_delay_s=2.0, rng=lambda: 0.5) == 0.2
    assert compute_backoff(attempt=2, base_delay_s=0.2, max_delay_s=2.0, rng=lambda: 0.5) == 0.4
    # Cap: attempt 10 would be 0.2 * 2**9 = 102.4 without the cap.
    assert (
        compute_backoff(attempt=10, base_delay_s=0.2, max_delay_s=2.0, rng=lambda: 0.5)
        == 2.0
    )
    # Jitter: rng=0.0 -> 0.5x, rng=1.0 -> 1.5x.
    assert compute_backoff(attempt=1, base_delay_s=1.0, max_delay_s=10.0, rng=lambda: 0.0) == 0.5
    assert compute_backoff(attempt=1, base_delay_s=1.0, max_delay_s=10.0, rng=lambda: 1.0) == 1.5
