"""Bounded specialist runner: timeout, capped retries, exponential backoff with jitter.

The runner turns an expected specialist failure into a ``SpecialistResult`` instead of an
unhandled exception, logs one structured line per attempt, and never retries a
non-transient error. Attempts are hard-capped at 3 so a retry storm cannot amplify an
outage, and a per-node deadline stops sleeping once the budget is gone.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agents.contracts import (
    PermanentError,
    SpecialistError,
    SpecialistResult,
    TransientError,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS_CAP = 3
DEFAULT_TIMEOUT_CODE = "specialist_timeout"


@dataclass
class SpecialistMetrics:
    """Per-workflow specialist counters for the summary log event."""

    calls: int = 0
    retries: int = 0
    failures: int = 0
    started_at: float = field(default_factory=time.perf_counter)

    def record_attempt(self, *, attempt: int, failed: bool) -> None:
        if attempt == 1:
            self.calls += 1
        else:
            self.retries += 1
        if failed:
            self.failures += 1

    def summary(self) -> dict[str, int]:
        return {
            "specialist_calls": self.calls,
            "specialist_retries": self.retries,
            "specialist_failures": self.failures,
            "elapsed_ms": int((time.perf_counter() - self.started_at) * 1000),
        }


def compute_backoff(
    *,
    attempt: int,
    base_delay_s: float,
    max_delay_s: float,
    rng: Callable[[], float] = random.random,
) -> float:
    """Full jitter in [0.5x, 1.5x] of the capped exponential delay."""
    delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
    return delay * (0.5 + rng())


def _source_ids_of(
    data: object,
    source_ids_of: Callable[[object], tuple[str, ...]] | None,
) -> tuple[str, ...]:
    if source_ids_of is not None:
        return tuple(source_ids_of(data))
    ids = getattr(data, "source_ids", None)
    return tuple(ids) if ids else ()


async def run_specialist[T](
    *,
    name: str,
    operation: Callable[[], Awaitable[T]],
    timeout_s: float,
    correlation_id: str,
    max_attempts: int = 3,
    base_delay_s: float = 0.2,
    max_delay_s: float = 2.0,
    deadline_s: float | None = None,
    thread_id: str | None = None,
    timeout_code: str | None = None,
    metrics: SpecialistMetrics | None = None,
    source_ids_of: Callable[[T], tuple[str, ...]] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: Callable[[], float] = random.random,
) -> SpecialistResult[T]:
    """Run ``operation`` under a per-call timeout, retry budget, and node deadline."""
    started = time.perf_counter()
    attempts_allowed = max(1, min(max_attempts, MAX_ATTEMPTS_CAP))
    timeout_error_code = timeout_code or f"{name}_timeout"
    attempts = 0
    last_error: SpecialistError | None = None
    source_ids: tuple[str, ...] = ()

    def budget_remaining_ms() -> int | None:
        if deadline_s is None:
            return None
        return max(0, int((deadline_s - (time.perf_counter() - started)) * 1000))

    def log_attempt(
        *, attempt: int, outcome: str, latency_ms: int, error: SpecialistError | None
    ) -> None:
        logger.info(
            "specialist attempt",
            extra={
                "correlation_id": correlation_id,
                "thread_id": thread_id,
                "specialist": name,
                "attempt": attempt,
                "outcome": outcome,
                "latency_ms": latency_ms,
                "error_code": error.code if error is not None else None,
                "budget_remaining_ms": budget_remaining_ms(),
            },
        )

    for attempt in range(1, attempts_allowed + 1):
        if deadline_s is not None and (time.perf_counter() - started) >= deadline_s:
            break

        attempts = attempt
        attempt_started = time.perf_counter()
        timeout = timeout_s
        if deadline_s is not None:
            timeout = min(
                timeout_s, max(0.0, deadline_s - (time.perf_counter() - started))
            )

        error: SpecialistError | None = None
        data: T | None = None
        try:
            data = await asyncio.wait_for(operation(), timeout=timeout)
        except SpecialistError as exc:
            error = exc
        except TimeoutError:
            error = TransientError("specialist call timed out", code=timeout_error_code)
        except Exception as exc:
            logger.warning(
                "specialist raised an unexpected exception",
                extra={
                    "correlation_id": correlation_id,
                    "thread_id": thread_id,
                    "specialist": name,
                    "attempt": attempt,
                    "outcome": "unexpected_error",
                    "error_code": "unexpected_specialist_error",
                },
                exc_info=True,
            )
            error = PermanentError(
                "unexpected specialist error",
                code="unexpected_specialist_error",
                details={"cause": type(exc).__name__},
            )

        attempt_ms = int((time.perf_counter() - attempt_started) * 1000)

        if error is None:
            source_ids = _source_ids_of(data, source_ids_of)
            log_attempt(attempt=attempt, outcome="success", latency_ms=attempt_ms, error=None)
            if metrics is not None:
                metrics.record_attempt(attempt=attempt, failed=False)
            return SpecialistResult.success(
                data,  # type: ignore[arg-type]
                attempts=attempt,
                latency_ms=int((time.perf_counter() - started) * 1000),
                source_ids=source_ids,
            )

        last_error = error
        log_attempt(attempt=attempt, outcome="error", latency_ms=attempt_ms, error=error)
        if metrics is not None:
            metrics.record_attempt(attempt=attempt, failed=True)

        if not error.transient:
            break
        if attempt >= attempts_allowed:
            break

        delay = compute_backoff(
            attempt=attempt, base_delay_s=base_delay_s, max_delay_s=max_delay_s, rng=rng
        )
        if deadline_s is not None and (
            time.perf_counter() + delay >= started + deadline_s
        ):
            # No budget left for the backoff sleep plus another attempt: stop early.
            break
        await sleep(delay)

    if last_error is None:
        last_error = TransientError(
            "specialist deadline exhausted before the first attempt",
            code=timeout_error_code,
        )
    return SpecialistResult.failure(
        last_error,
        attempts=attempts,
        latency_ms=int((time.perf_counter() - started) * 1000),
        source_ids=source_ids,
    )
