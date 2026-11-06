"""Deterministic validation of comparison output and recommendations.

Validation never calls an LLM. Blocking issues prevent approval; warnings become
recommendation caveats. Every issue uses a machine-readable code.
"""

from decimal import Decimal
from typing import Any

from app.services.comparison_service import ComparisonService

REQUIRED_EVIDENCE_FIELDS = ("chunk_id", "document_id", "version", "section_path")
DISALLOWED_EVIDENCE_STATUSES = {"obsolete", "draft"}


def _issue(code: str, message: str, *, severity: str = "blocking") -> dict[str, str]:
    return {"code": code, "message": message, "severity": severity}


class RecommendationValidator:
    def __init__(self, comparison_service: ComparisonService | None = None) -> None:
        self.comparison_service = comparison_service or ComparisonService()

    def validate(
        self,
        *,
        request: dict[str, Any],
        comparison: dict[str, Any] | None,
        recommendation: dict[str, Any] | None,
        policy_status: dict[str, Any] | None,
        policy_evidence: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        quantity = int(request.get("quantity") or 0)
        if quantity <= 0 or not request.get("product_id") or not request.get("category"):
            issues.append(
                _issue(
                    "missing_request_info",
                    "request is missing a product, category, or positive quantity",
                )
            )

        eligible = (comparison or {}).get("eligible") or []
        if comparison is None or not eligible:
            issues.append(
                _issue("no_eligible_supplier", "no supplier passed the eligibility rules")
            )

        if recommendation is None:
            issues.append(
                _issue("recommendation_missing", "no recommendation was produced")
            )
        else:
            self._validate_recommendation(
                request=request,
                comparison=comparison or {},
                recommendation=recommendation,
                issues=issues,
            )

        self._validate_policy(
            policy_status=policy_status or {},
            policy_evidence=policy_evidence or [],
            issues=issues,
        )

        sufficient = not any(
            issue["severity"] == "blocking" for issue in issues
        )
        return {"sufficient": sufficient, "issues": issues}

    def _validate_recommendation(
        self,
        *,
        request: dict[str, Any],
        comparison: dict[str, Any],
        recommendation: dict[str, Any],
        issues: list[dict[str, str]],
    ) -> None:
        recommended = comparison.get("recommended") or {}
        eligible_ids = {item["supplier_id"] for item in comparison.get("eligible") or []}
        supplier_id = recommendation.get("supplier_id")
        if supplier_id not in eligible_ids:
            issues.append(
                _issue(
                    "recommendation_not_eligible",
                    f"recommended supplier {supplier_id!r} is not eligible",
                )
            )
            return

        version = recommendation.get("version")
        if not isinstance(version, int) or version <= 0:
            issues.append(
                _issue(
                    "invalid_recommendation_version",
                    "recommendation version must be a positive integer",
                )
            )

        if not recommendation.get("persisted"):
            issues.append(
                _issue(
                    "recommendation_not_persisted",
                    "recommendation must be persisted before approval",
                )
            )

        rationale = comparison.get("rationale") or {}
        min_price = rationale.get("min_eligible_unit_price")
        min_delivery = rationale.get("min_eligible_delivery_days")
        try:
            components = self.comparison_service.score_components(
                unit_price=Decimal(str(recommended["unit_price"])),
                delivery_days=int(recommended["delivery_days"]),
                risk_level=str(recommended.get("risk_level", "unknown")),
                min_price=Decimal(str(min_price)),
                min_delivery=int(min_delivery),
                quantity=int(request["quantity"]),
            )
            expected_score = components["total_score"]
            if Decimal(str(recommendation["score"])) != expected_score:
                issues.append(
                    _issue(
                        "score_mismatch",
                        "recommendation score does not match deterministic recomputation",
                    )
                )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            issues.append(
                _issue(
                    "score_mismatch",
                    "recommendation score could not be recomputed from its inputs",
                )
            )

        try:
            unit_price = Decimal(str(recommendation["unit_price"]))
            expected_cost = (unit_price * Decimal(int(request["quantity"]))).quantize(
                Decimal("0.01")
            )
            if Decimal(str(recommendation["total_cost"])) != expected_cost:
                issues.append(
                    _issue(
                        "total_cost_mismatch",
                        "recommendation total cost is arithmetically incorrect",
                    )
                )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            issues.append(
                _issue("total_cost_mismatch", "recommendation total cost is invalid")
            )

        constraints = request.get("constraints") or {}
        max_delivery = constraints.get("max_delivery_days")
        if max_delivery is not None and int(recommendation["delivery_days"]) > int(
            max_delivery
        ):
            issues.append(
                _issue("constraint_violation", "recommendation exceeds max delivery days")
            )
        max_price = constraints.get("max_unit_price")
        if max_price is not None and Decimal(str(recommendation["unit_price"])) > Decimal(
            str(max_price)
        ):
            issues.append(
                _issue("constraint_violation", "recommendation exceeds max unit price")
            )

    def _validate_policy(
        self,
        *,
        policy_status: dict[str, Any],
        policy_evidence: list[dict[str, Any]],
        issues: list[dict[str, str]],
    ) -> None:
        if policy_status.get("inconclusive") or not policy_evidence:
            reason = policy_status.get("reason") or "no evidence returned"
            issues.append(
                _issue(
                    "weak_policy_evidence",
                    f"policy evidence is inconclusive: {reason}",
                )
            )
            return

        for index, item in enumerate(policy_evidence):
            missing = [
                field for field in REQUIRED_EVIDENCE_FIELDS if not item.get(field)
            ]
            if missing:
                issues.append(
                    _issue(
                        "evidence_missing_fields",
                        f"evidence item {index} is missing {', '.join(missing)}",
                    )
                )
            status = item.get("status")
            if status is not None and str(status).lower() in DISALLOWED_EVIDENCE_STATUSES:
                issues.append(
                    _issue(
                        "obsolete_evidence",
                        f"evidence item {index} has disallowed status {status!r}",
                    )
                )
