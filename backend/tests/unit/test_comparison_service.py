"""Table-driven tests for deterministic eligibility, scoring, and ranking (step 3.3)."""

import json
from typing import Any

import pytest
from app.services.comparison_service import ComparisonInputError, ComparisonService
from app.services.scoring_config import SCORING_VERSION

AS_OF = "2026-01-15"


def make_request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "product_id": "PRD0001",
        "product_name": "Essential Monitor",
        "category": "electronics",
        "quantity": 100,
        "currency": "INR",
        "constraints": {},
    }
    request.update(overrides)
    return request


def make_candidate(**overrides: Any) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "supplier_id": "SUP0001",
        "supplier_name": "Apex Components Pvt Ltd",
        "supplier_category": "electronics",
        "supplier_status": "active",
        "quotation_id": "QTN00001",
        "product_id": "PRD0001",
        "unit_price": "100.00",
        "currency": "INR",
        "available_quantity": 1000,
        "delivery_days": 10,
        "valid_until": "2026-06-01",
        "profile": {
            "certifications": ["ISO9001"],
            "compliance": {"risk_level": "low", "verification_status": "verified"},
        },
    }
    candidate.update(overrides)
    return candidate


def compare(request, candidates, *, as_of: str = AS_OF) -> dict[str, Any]:
    return ComparisonService().compare(request, candidates, as_of=as_of)


def test_cheapest_wins_when_delivery_and_risk_equal() -> None:
    cheap = make_candidate(supplier_id="SUP0001", unit_price="100.00")
    pricey = make_candidate(supplier_id="SUP0002", quotation_id="QTN00002", unit_price="110.00")

    result = compare(make_request(), [pricey, cheap])

    assert result["recommended"]["supplier_id"] == "SUP0001"
    assert result["eligible_count"] == 2
    assert result["reason"] is None


def test_faster_delivery_can_beat_higher_price() -> None:
    slow = make_candidate(supplier_id="SUP0001", unit_price="100.00", delivery_days=10)
    fast = make_candidate(
        supplier_id="SUP0002", quotation_id="QTN00002", unit_price="105.00", delivery_days=5
    )

    result = compare(make_request(), [slow, fast])

    # price 100/delivery 10 scores ~85; price 105/delivery 5 scores ~97 under 0.55/0.30/0.15.
    scores = scores_by_supplier(result)
    assert result["recommended"]["supplier_id"] == "SUP0002"
    assert scores["SUP0002"] > scores["SUP0001"]


def scores_by_supplier(result: dict[str, Any]) -> dict[str, float]:
    return {item["supplier_id"]: float(item["total_score"]) for item in result["eligible"]}


def test_expired_quotation_excluded_even_if_cheapest() -> None:
    expired = make_candidate(
        supplier_id="SUP0001", unit_price="50.00", valid_until="2026-01-01"
    )
    current = make_candidate(supplier_id="SUP0002", quotation_id="QTN00002", unit_price="110.00")

    result = compare(make_request(), [expired, current])

    assert result["recommended"]["supplier_id"] == "SUP0002"
    excluded = {item["supplier_id"]: item["reasons"] for item in result["excluded"]}
    assert excluded["SUP0001"] == ["expired_quotation"]


def test_insufficient_quantity_excluded() -> None:
    small = make_candidate(supplier_id="SUP0001", available_quantity=99)
    big = make_candidate(supplier_id="SUP0002", quotation_id="QTN00002", unit_price="110.00")

    result = compare(make_request(quantity=100), [small, big])

    assert result["recommended"]["supplier_id"] == "SUP0002"
    excluded = {item["supplier_id"]: item["reasons"] for item in result["excluded"]}
    assert excluded["SUP0001"] == ["insufficient_quantity"]


def test_missing_required_certification_excluded() -> None:
    no_cert = make_candidate(supplier_id="SUP0001", profile={"certifications": []})
    certified = make_candidate(
        supplier_id="SUP0002", quotation_id="QTN00002", unit_price="110.00"
    )
    request = make_request(constraints={"required_certifications": ["ISO9001"]})

    result = compare(request, [no_cert, certified])

    assert result["recommended"]["supplier_id"] == "SUP0002"
    excluded = {item["supplier_id"]: item["reasons"] for item in result["excluded"]}
    assert excluded["SUP0001"] == ["missing_certification"]


def test_high_risk_supplier_penalized_but_not_excluded() -> None:
    low_risk = make_candidate(supplier_id="SUP0001", unit_price="100.00")
    high_risk = make_candidate(
        supplier_id="SUP0002",
        quotation_id="QTN00002",
        unit_price="90.00",
        profile={
            "certifications": ["ISO9001"],
            "compliance": {"risk_level": "high", "verification_status": "verified"},
        },
    )

    result = compare(make_request(), [low_risk, high_risk])

    ids = {item["supplier_id"] for item in result["eligible"]}
    assert ids == {"SUP0001", "SUP0002"}
    scores = scores_by_supplier(result)
    assert scores["SUP0001"] > scores["SUP0002"]
    assert result["recommended"]["supplier_id"] == "SUP0001"


def test_tie_break_is_deterministic() -> None:
    first = make_candidate(supplier_id="SUP0001")
    second = make_candidate(supplier_id="SUP0002", quotation_id="QTN00002")

    result = compare(make_request(), [second, first])

    scores = scores_by_supplier(result)
    assert scores["SUP0001"] == scores["SUP0002"]
    assert result["recommended"]["supplier_id"] == "SUP0001"

    reversed_result = compare(make_request(), [first, second])
    assert reversed_result["recommended"]["supplier_id"] == "SUP0001"


def test_same_inputs_produce_byte_identical_output() -> None:
    request = make_request()
    candidates = [
        make_candidate(supplier_id="SUP0001", unit_price="100.00"),
        make_candidate(supplier_id="SUP0002", quotation_id="QTN00002", unit_price="104.50"),
        make_candidate(
            supplier_id="SUP0003",
            quotation_id="QTN00003",
            unit_price="98.00",
            delivery_days=30,
        ),
    ]

    first = compare(request, candidates)
    second = compare(request, list(reversed(candidates)))

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["rationale"]["scoring_version"] == SCORING_VERSION


def test_empty_eligible_set_returns_structured_result() -> None:
    result = compare(make_request(), [])

    assert result["reason"] == "no_eligible_supplier"
    assert result["eligible_count"] == 0
    assert result["eligible"] == []
    assert result["recommended"] is None
    assert result["rationale"]["recommended_supplier_id"] is None


def test_all_excluded_returns_no_eligible_supplier() -> None:
    inactive = make_candidate(supplier_id="SUP0001", supplier_status="inactive")

    result = compare(make_request(), [inactive])

    assert result["reason"] == "no_eligible_supplier"
    assert result["excluded"][0]["reasons"] == ["inactive_supplier"]


def test_eligibility_reason_codes_for_constraints() -> None:
    too_slow = make_candidate(delivery_days=40)
    over_cap = make_candidate(
        supplier_id="SUP0002", quotation_id="QTN00002", unit_price="500.00"
    )
    wrong_currency = make_candidate(
        supplier_id="SUP0003", quotation_id="QTN00003", currency="USD"
    )
    rejected_profile = make_candidate(
        supplier_id="SUP0004",
        quotation_id="QTN00004",
        profile={
            "certifications": ["ISO9001"],
            "compliance": {"risk_level": "low", "verification_status": "rejected"},
        },
    )
    withdrawn = make_candidate(supplier_id="SUP0005", quotation_id="QTN00005", withdrawn=True)
    request = make_request(constraints={"max_delivery_days": 30, "max_unit_price": "200.00"})

    result = compare(
        request, [too_slow, over_cap, wrong_currency, rejected_profile, withdrawn]
    )

    reasons = {item["supplier_id"]: item["reasons"] for item in result["excluded"]}
    assert reasons["SUP0001"] == ["delivery_too_slow"]
    assert reasons["SUP0002"] == ["price_above_cap"]
    assert reasons["SUP0003"] == ["currency_mismatch"]
    assert reasons["SUP0004"] == ["unverified_supplier"]
    assert reasons["SUP0005"] == ["withdrawn_quotation"]
    assert result["recommended"] is None


def test_category_mismatch_excluded() -> None:
    furniture_supplier = make_candidate(supplier_category="furniture")

    result = compare(make_request(), [furniture_supplier])

    assert result["reason"] == "no_eligible_supplier"
    assert result["excluded"][0]["reasons"] == ["category_mismatch"]


def test_structural_input_errors_raise() -> None:
    with pytest.raises(ComparisonInputError):
        compare(make_request(quantity=0), [make_candidate()])
    with pytest.raises(ComparisonInputError):
        compare(make_request(product_id=""), [make_candidate()])
    with pytest.raises(ComparisonInputError):
        compare(make_request(), [make_candidate(unit_price="not-a-number")])


def test_score_components_clamp_and_quantize() -> None:
    from decimal import Decimal

    service = ComparisonService()
    components = service.score_components(
        unit_price=Decimal("1"),
        delivery_days=1,
        risk_level="unknown",
        min_price=Decimal("1000"),
        min_delivery=100,
        quantity=1,
    )

    assert components["price_score"] == Decimal("100.00")
    assert components["delivery_score"] == Decimal("100.00")
    assert components["risk_score"] == Decimal("50.00")
    # 0.55*100 + 0.30*100 + 0.15*50 = 92.50 for an unknown risk level.
    assert components["total_score"] == Decimal("92.50")

    low_risk = service.score_components(
        unit_price=Decimal("1"),
        delivery_days=1,
        risk_level="low",
        min_price=Decimal("1000"),
        min_delivery=100,
        quantity=1,
    )
    assert low_risk["total_score"] == Decimal("100.00")

    with pytest.raises(ComparisonInputError):
        service.score_components(
            unit_price=Decimal("1"),
            delivery_days=0,
            risk_level="low",
            min_price=Decimal("1"),
            min_delivery=1,
            quantity=1,
        )
