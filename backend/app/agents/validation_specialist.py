"""Validation specialist: recommendation completeness, evidence, and arithmetic checks.

Never calls an LLM, never overrides authorization or approval, and never mutates the
recommendation — it only reports issues with stable machine-readable codes.
"""

from __future__ import annotations

from app.agents.contracts import (
    PermanentError,
    ValidationRequest,
    ValidationResult,
)
from app.services.comparison_service import ComparisonService
from app.services.recommendation_validation_service import RecommendationValidator


class ValidationSpecialist:
    """Deterministic recommendation validation behind a narrow contract."""

    name = "validate_recommendation"

    def __init__(self, validator: RecommendationValidator | None = None) -> None:
        self.validator = validator or RecommendationValidator(ComparisonService())

    async def validate(self, request: ValidationRequest) -> ValidationResult:
        try:
            payload = self.validator.validate(
                request=dict(request.request),
                comparison=dict(request.comparison) if request.comparison else None,
                recommendation=(
                    dict(request.recommendation) if request.recommendation else None
                ),
                policy_status=dict(request.policy_status),
                policy_evidence=[item.to_dict() for item in request.policy_evidence],
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PermanentError(
                "validation inputs are malformed",
                code="invalid_validation_input",
                details={"cause": type(exc).__name__},
            ) from exc
        return ValidationResult.from_dict(payload)
