"""Single source of truth for deterministic scoring and eligibility.

These values are intentionally code, not configuration: changing a weight changes the
meaning of every recommendation version and must be a reviewed code change that bumps
``SCORING_VERSION``.
"""

from decimal import Decimal

SCORING_VERSION = "1.0"
DEFAULT_CURRENCY = "INR"
ELIGIBLE_SUPPLIER_STATUS = "active"

WEIGHTS: dict[str, Decimal] = {
    "price": Decimal("0.55"),
    "delivery": Decimal("0.30"),
    "risk": Decimal("0.15"),
}

RISK_SCORES: dict[str, Decimal] = {
    "low": Decimal("100"),
    "medium": Decimal("70"),
    "high": Decimal("40"),
    "unknown": Decimal("50"),
}

# Explicit product-category -> supplier-category mapping. Do not infer this at runtime.
ALLOWED_SUPPLIER_CATEGORIES: dict[str, frozenset[str]] = {
    "electronics": frozenset({"electronics"}),
    "furniture": frozenset({"furniture"}),
    "it_hardware": frozenset({"it_hardware"}),
    "office_supplies": frozenset({"office_supplies"}),
}

ELIGIBILITY_REASON_CODES = (
    "inactive_supplier",
    "expired_quotation",
    "insufficient_quantity",
    "delivery_too_slow",
    "price_above_cap",
    "missing_certification",
    "currency_mismatch",
    "category_mismatch",
    "unverified_supplier",
    "withdrawn_quotation",
    "invalid_delivery",
)
