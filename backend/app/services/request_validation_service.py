"""Deterministic request validation used by the first workflow node."""

from decimal import Decimal, InvalidOperation
from typing import Any


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "severity": "blocking"}


class RequestValidator:
    def validate(self, request: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        product_id = request.get("product_id")
        if not product_id:
            issues.append(_issue("missing_product", "product_id is required"))
        if not request.get("category"):
            issues.append(_issue("missing_category", "product category is required"))

        quantity = request.get("quantity")
        try:
            if int(quantity) <= 0:
                issues.append(_issue("invalid_quantity", "quantity must be positive"))
        except (TypeError, ValueError):
            issues.append(_issue("invalid_quantity", "quantity must be an integer"))

        constraints = request.get("constraints") or {}
        if not isinstance(constraints, dict):
            issues.append(_issue("invalid_constraints", "constraints must be an object"))
        else:
            max_delivery = constraints.get("max_delivery_days")
            if max_delivery is not None:
                try:
                    if int(max_delivery) < 0:
                        issues.append(
                            _issue(
                                "invalid_constraints",
                                "max_delivery_days must be non-negative",
                            )
                        )
                except (TypeError, ValueError):
                    issues.append(
                        _issue("invalid_constraints", "max_delivery_days must be an integer")
                    )
            max_price = constraints.get("max_unit_price")
            if max_price is not None:
                try:
                    if Decimal(str(max_price)) < 0:
                        issues.append(
                            _issue(
                                "invalid_constraints",
                                "max_unit_price must be non-negative",
                            )
                        )
                except (InvalidOperation, TypeError, ValueError):
                    issues.append(
                        _issue("invalid_constraints", "max_unit_price must be a decimal")
                    )

        return {"valid": not issues, "issues": issues}
