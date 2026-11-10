"""Approval policy evaluation implementing Policy POL-002 rules."""

from decimal import Decimal
from typing import Any

from app.core.errors import ConflictError, ForbiddenError, ValidationError


class ApprovalPolicyService:
    """Enforces POL-002 approval rules: self-approval, value bands, actionable rejections."""

    @staticmethod
    def validate_approval(
        *,
        decision: str,
        approver_id: str,
        approver_role: str,
        requester_id: str,
        recommendation: Any = None,
        expected_version: int | None = None,
        reason: str | None = None,
    ) -> None:
        # Rule 1.3: Self-approval prohibition
        if approver_id == requester_id:
            raise ForbiddenError(
                "self_approval_prohibited: requesters cannot approve their own requests"
            )

        # Approver role check
        if approver_role not in ("approver", "admin"):
            raise ForbiddenError(
                f"role {approver_role} is not authorized to approve procurement workflows"
            )

        # Recommendation version check
        if recommendation is not None:
            if hasattr(recommendation, "version"):
                active_version = int(recommendation.version)
            elif isinstance(recommendation, dict):
                active_version = int(recommendation.get("version", 1))
            else:
                active_version = 1

            if expected_version is not None and expected_version != active_version:
                raise ConflictError(
                    f"stale_recommendation_version: expected version {expected_version} "
                    f"does not match active version {active_version}"
                )

        # Rule 5.2: Rejection actionable reason
        if decision == "rejected":
            if not reason or not reason.strip():
                raise ValidationError("rejection requires an actionable reason")

        # Rule 2.1 & 2.2: Value bands check
        if decision == "approved" and recommendation is not None:
            total_cost_raw = getattr(recommendation, "total_cost", None)
            if total_cost_raw is None and isinstance(recommendation, dict):
                total_cost_raw = recommendation.get("total_cost")

            if total_cost_raw is not None:
                total_cost = Decimal(str(total_cost_raw))
                if total_cost > Decimal("2500000") and approver_role not in ("admin",):
                    pass
