"""Deterministic supplier eligibility, scoring, and ranking.

No LangGraph, FastAPI, or LLM code belongs here. The same inputs must always produce the
same ranking, score, and rationale. Money is handled with ``Decimal`` and converted to
strings only at the JSON state boundary.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.services.scoring_config import (
    ALLOWED_SUPPLIER_CATEGORIES,
    DEFAULT_CURRENCY,
    ELIGIBLE_SUPPLIER_STATUS,
    RISK_SCORES,
    SCORING_VERSION,
    WEIGHTS,
)

SCORE_QUANT = Decimal("0.01")
MONEY_QUANT = Decimal("0.01")


class ComparisonInputError(ValueError):
    """Raised when the request or a candidate is structurally invalid."""


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ComparisonInputError(f"invalid decimal for {field}: {value!r}") from exc


def _as_date(value: Any, *, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ComparisonInputError(f"invalid date for {field}: {value!r}") from exc


def _quantize(value: Decimal, quantum: Decimal = SCORE_QUANT) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, low: Decimal = Decimal("0"), high: Decimal = Decimal("100")) -> Decimal:
    return max(low, min(high, value))


def _risk_level(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "unknown"
    compliance = profile.get("compliance")
    if not isinstance(compliance, dict):
        return "unknown"
    level = str(compliance.get("risk_level", "unknown")).lower()
    return level if level in RISK_SCORES else "unknown"


def _verification_status(profile: dict[str, Any] | None) -> str | None:
    if not profile:
        return None
    compliance = profile.get("compliance")
    if not isinstance(compliance, dict):
        return None
    status = compliance.get("verification_status")
    return str(status).lower() if status is not None else None


def _certifications(profile: dict[str, Any] | None) -> set[str]:
    if not profile:
        return set()
    values = profile.get("certifications") or []
    return {str(value) for value in values}


def _constraints(request: dict[str, Any]) -> dict[str, Any]:
    constraints = request.get("constraints") or {}
    if not isinstance(constraints, dict):
        raise ComparisonInputError("request constraints must be an object")
    return constraints


class ComparisonService:
    """Pure deterministic comparison engine."""

    scoring_version = SCORING_VERSION

    def score_components(
        self,
        *,
        unit_price: Decimal,
        delivery_days: int,
        risk_level: str,
        min_price: Decimal,
        min_delivery: int,
        quantity: int,
    ) -> dict[str, Decimal]:
        if quantity <= 0:
            raise ComparisonInputError("quantity must be positive")
        if delivery_days <= 0:
            raise ComparisonInputError("delivery_days must be positive")

        if unit_price <= 0:
            price_score = Decimal("100")
        else:
            price_score = _clamp((min_price / unit_price) * Decimal("100"))
        delivery_score = _clamp((Decimal(min_delivery) / Decimal(delivery_days)) * Decimal("100"))
        risk_score = _clamp(RISK_SCORES.get(risk_level, RISK_SCORES["unknown"]))

        total_score = (
            WEIGHTS["price"] * price_score
            + WEIGHTS["delivery"] * delivery_score
            + WEIGHTS["risk"] * risk_score
        )
        return {
            "price_score": _quantize(price_score),
            "delivery_score": _quantize(delivery_score),
            "risk_score": _quantize(risk_score),
            "total_score": _quantize(_clamp(total_score)),
        }

    def _eligibility(
        self,
        request: dict[str, Any],
        candidate: dict[str, Any],
        *,
        as_of: date,
    ) -> list[str]:
        reasons: list[str] = []
        constraints = _constraints(request)
        currency = str(request.get("currency") or DEFAULT_CURRENCY)

        if str(candidate.get("supplier_status", "")).lower() != ELIGIBLE_SUPPLIER_STATUS:
            reasons.append("inactive_supplier")

        valid_until = _as_date(candidate.get("valid_until"), field="valid_until")
        if valid_until < as_of:
            reasons.append("expired_quotation")

        available = int(candidate.get("available_quantity", 0))
        quantity = int(request.get("quantity", 0))
        if available < quantity:
            reasons.append("insufficient_quantity")

        delivery_days = int(candidate.get("delivery_days", 0))
        max_delivery_days = constraints.get("max_delivery_days")
        if max_delivery_days is not None and delivery_days > int(max_delivery_days):
            reasons.append("delivery_too_slow")
        if delivery_days <= 0:
            reasons.append("invalid_delivery")

        unit_price = _decimal(candidate.get("unit_price"), field="unit_price")
        max_unit_price = constraints.get("max_unit_price")
        if max_unit_price is not None and unit_price > _decimal(
            max_unit_price, field="max_unit_price"
        ):
            reasons.append("price_above_cap")

        required = {
            str(value).replace("-", "").replace("_", "").strip().upper()
            for value in constraints.get("required_certifications") or []
        }
        if required:
            profile_certifications = {
                str(value).replace("-", "").replace("_", "").strip().upper()
                for value in _certifications(candidate.get("profile"))
            }
            if not required.issubset(profile_certifications):
                reasons.append("missing_certification")

        if str(candidate.get("currency", DEFAULT_CURRENCY)) != currency:
            reasons.append("currency_mismatch")

        product_category = str(request.get("category", ""))
        allowed = ALLOWED_SUPPLIER_CATEGORIES.get(product_category, frozenset())
        if str(candidate.get("supplier_category", "")) not in allowed:
            reasons.append("category_mismatch")

        if _verification_status(candidate.get("profile")) == "rejected":
            reasons.append("unverified_supplier")

        if bool(candidate.get("withdrawn")):
            reasons.append("withdrawn_quotation")

        return reasons

    def compare(
        self,
        request: dict[str, Any],
        candidates: list[dict[str, Any]],
        *,
        as_of: str,
    ) -> dict[str, Any]:
        request_date = _as_date(as_of, field="as_of")
        quantity = int(request.get("quantity", 0))
        if quantity <= 0:
            raise ComparisonInputError("quantity must be positive")
        if not request.get("product_id"):
            raise ComparisonInputError("request product_id is required")

        eligible_raw: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []

        for candidate in candidates:
            reasons = self._eligibility(request, candidate, as_of=request_date)
            if reasons:
                excluded.append(
                    {
                        "supplier_id": str(candidate["supplier_id"]),
                        "supplier_name": str(candidate.get("supplier_name", "")),
                        "quotation_id": str(candidate.get("quotation_id", "")),
                        "reasons": reasons,
                    }
                )
                continue
            eligible_raw.append(candidate)

        min_price = min(
            (_decimal(item["unit_price"], field="unit_price") for item in eligible_raw),
            default=None,
        )
        min_delivery = min(
            (int(item["delivery_days"]) for item in eligible_raw),
            default=None,
        )

        eligible: list[dict[str, Any]] = []
        for candidate in eligible_raw:
            unit_price = _decimal(candidate["unit_price"], field="unit_price")
            delivery_days = int(candidate["delivery_days"])
            risk_level = _risk_level(candidate.get("profile"))
            assert min_price is not None and min_delivery is not None
            components = self.score_components(
                unit_price=unit_price,
                delivery_days=delivery_days,
                risk_level=risk_level,
                min_price=min_price,
                min_delivery=min_delivery,
                quantity=quantity,
            )
            total_cost = _quantize(unit_price * Decimal(quantity), MONEY_QUANT)
            eligible.append(
                {
                    "supplier_id": str(candidate["supplier_id"]),
                    "supplier_name": str(candidate.get("supplier_name", "")),
                    "supplier_category": str(candidate.get("supplier_category", "")),
                    "quotation_id": str(candidate.get("quotation_id", "")),
                    "unit_price": str(unit_price),
                    "currency": str(candidate.get("currency", DEFAULT_CURRENCY)),
                    "available_quantity": int(candidate.get("available_quantity", 0)),
                    "delivery_days": delivery_days,
                    "valid_until": _as_date(
                        candidate.get("valid_until"), field="valid_until"
                    ).isoformat(),
                    "risk_level": risk_level,
                    "total_cost": str(total_cost),
                    "components": {key: str(value) for key, value in components.items()},
                    "total_score": str(components["total_score"]),
                }
            )

        eligible.sort(
            key=lambda item: (
                -Decimal(item["total_score"]),
                Decimal(item["total_cost"]),
                int(item["delivery_days"]),
                item["supplier_id"],
            )
        )
        excluded.sort(key=lambda item: (item["supplier_id"], item["quotation_id"]))

        recommended = eligible[0] if eligible else None
        rationale: dict[str, Any] = {
            "scoring_version": SCORING_VERSION,
            "as_of": request_date.isoformat(),
            "currency": str(request.get("currency") or DEFAULT_CURRENCY),
            "weights": {key: str(value) for key, value in WEIGHTS.items()},
            "risk_scores": {key: str(value) for key, value in RISK_SCORES.items()},
            "min_eligible_unit_price": str(min_price) if min_price is not None else None,
            "min_eligible_delivery_days": min_delivery,
            "eligible": eligible,
            "excluded": excluded,
            "recommended_supplier_id": (
                recommended["supplier_id"] if recommended is not None else None
            ),
            "recommended_quotation_id": (
                recommended["quotation_id"] if recommended is not None else None
            ),
        }

        return {
            "reason": None if recommended is not None else "no_eligible_supplier",
            "eligible_count": len(eligible),
            "eligible": eligible,
            "excluded": excluded,
            "recommended": recommended,
            "rationale": rationale,
        }
