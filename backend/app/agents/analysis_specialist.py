"""Deterministic analysis specialist: eligibility, scoring, and ranking.

Pure and side-effect free: no I/O, no LLM, no clock beyond the injected ``as_of``. It
does not retrieve policy evidence and does not write recommendation prose — it isolates
the highest-risk business logic so identical inputs provably produce identical output.
"""

from __future__ import annotations

from app.agents.contracts import (
    ComparisonRequest,
    ComparisonResult,
    PermanentError,
)
from app.services.comparison_service import ComparisonInputError, ComparisonService


class AnalysisSpecialist:
    """Applies Phase 3 eligibility rules and scoring behind a narrow contract."""

    name = "compare_options"

    def __init__(self, comparison: ComparisonService | None = None) -> None:
        self.comparison = comparison or ComparisonService()

    async def compare(self, request: ComparisonRequest) -> ComparisonResult:
        try:
            payload = self.comparison.compare(
                dict(request.request),
                [candidate.to_dict() for candidate in request.candidates],
                as_of=request.as_of,
            )
        except ComparisonInputError as exc:
            raise PermanentError(
                str(exc), code="invalid_comparison_input"
            ) from exc
        return ComparisonResult.from_dict(payload)
