"""Each validation issue code must be triggered at least once (step 3.5)."""

from typing import Any

from app.services.comparison_service import ComparisonService
from app.services.recommendation_validation_service import RecommendationValidator

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


def make_candidate() -> dict[str, Any]:
    return {
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


def make_evidence(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "chunk_id": "chunk-0001",
        "document_id": "POL-001",
        "version": "3.2",
        "title": "Procurement Policy",
        "section_path": "4.1 Thresholds",
        "text": "Purchases above threshold require approval.",
        "score": 0.05,
        "dense_rank": 1,
        "sparse_rank": 1,
        "source_path": "data/documents/policy-001.md",
        "effective_from": "2026-01-01",
        "status": "active",
        "classification": "internal",
        "injection_suspected": False,
    }
    item.update(overrides)
    return item


def baseline() -> dict[str, Any]:
    request = make_request()
    comparison = ComparisonService().compare(request, [make_candidate()], as_of=AS_OF)
    recommended = comparison["recommended"]
    recommendation = {
        "supplier_id": recommended["supplier_id"],
        "supplier_name": recommended["supplier_name"],
        "score": recommended["total_score"],
        "scoring_version": comparison["rationale"]["scoring_version"],
        "total_cost": recommended["total_cost"],
        "unit_price": recommended["unit_price"],
        "currency": recommended["currency"],
        "delivery_days": recommended["delivery_days"],
        "version": 1,
        "persisted": True,
        "evidence": [make_evidence()],
    }
    return {
        "request": request,
        "comparison": comparison,
        "recommendation": recommendation,
        "policy_status": {"inconclusive": False, "reason": None},
        "policy_evidence": [make_evidence()],
    }


def validate(**overrides: Any) -> dict[str, Any]:
    case = baseline()
    case.update(overrides)
    return RecommendationValidator().validate(
        request=case["request"],
        comparison=case["comparison"],
        recommendation=case["recommendation"],
        policy_status=case["policy_status"],
        policy_evidence=case["policy_evidence"],
    )


def codes(result: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def test_baseline_is_sufficient() -> None:
    result = validate()
    assert result["sufficient"] is True
    assert result["issues"] == []


def test_missing_request_info() -> None:
    result = validate(request=make_request(category=""))
    assert "missing_request_info" in codes(result)
    assert result["sufficient"] is False


def test_no_eligible_supplier() -> None:
    result = validate(
        comparison={"eligible": [], "recommended": None, "rationale": {}},
        recommendation=None,
    )
    assert "no_eligible_supplier" in codes(result)


def test_recommendation_missing() -> None:
    result = validate(recommendation=None)
    assert "recommendation_missing" in codes(result)


def test_recommendation_not_eligible() -> None:
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "supplier_id": "SUP9999"}
    result = validate(**case)
    assert "recommendation_not_eligible" in codes(result)


def test_invalid_recommendation_version() -> None:
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "version": 0}
    result = validate(**case)
    assert "invalid_recommendation_version" in codes(result)


def test_recommendation_not_persisted() -> None:
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "persisted": False}
    result = validate(**case)
    assert "recommendation_not_persisted" in codes(result)


def test_score_mismatch() -> None:
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "score": "1.00"}
    result = validate(**case)
    assert "score_mismatch" in codes(result)


def test_total_cost_mismatch() -> None:
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "total_cost": "0.01"}
    result = validate(**case)
    assert "total_cost_mismatch" in codes(result)


def test_constraint_violation() -> None:
    case = baseline()
    case["request"] = make_request(constraints={"max_delivery_days": 5})
    result = validate(**case)
    assert "constraint_violation" in codes(result)


def test_weak_policy_evidence_inconclusive() -> None:
    result = validate(
        policy_status={"inconclusive": True, "reason": "weak_evidence"},
        policy_evidence=[],
    )
    assert "weak_policy_evidence" in codes(result)
    assert result["sufficient"] is False


def test_weak_policy_evidence_empty_list() -> None:
    result = validate(policy_status={"inconclusive": False, "reason": None}, policy_evidence=[])
    assert "weak_policy_evidence" in codes(result)


def test_evidence_missing_fields() -> None:
    result = validate(policy_evidence=[make_evidence(section_path="")])
    assert "evidence_missing_fields" in codes(result)


def test_obsolete_evidence() -> None:
    result = validate(policy_evidence=[make_evidence(status="obsolete")])
    assert "obsolete_evidence" in codes(result)


def test_every_issue_code_is_covered() -> None:
    """Guard: the table above must keep covering the full blocking-code surface."""
    expected = {
        "missing_request_info",
        "no_eligible_supplier",
        "recommendation_missing",
        "recommendation_not_eligible",
        "recommendation_not_persisted",
        "invalid_recommendation_version",
        "score_mismatch",
        "total_cost_mismatch",
        "constraint_violation",
        "weak_policy_evidence",
        "evidence_missing_fields",
        "obsolete_evidence",
    }
    covered: set[str] = set()
    covered |= codes(validate(request=make_request(category="")))
    covered |= codes(
        validate(
            comparison={"eligible": [], "recommended": None, "rationale": {}},
            recommendation=None,
        )
    )
    covered |= codes(validate(recommendation=None))
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "supplier_id": "SUP9999"}
    covered |= codes(validate(**case))
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "version": 0}
    covered |= codes(validate(**case))
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "persisted": False}
    covered |= codes(validate(**case))
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "score": "1.00"}
    covered |= codes(validate(**case))
    case = baseline()
    case["recommendation"] = {**case["recommendation"], "total_cost": "0.01"}
    covered |= codes(validate(**case))
    case = baseline()
    case["request"] = make_request(constraints={"max_delivery_days": 5})
    covered |= codes(validate(**case))
    covered |= codes(validate(policy_evidence=[make_evidence(section_path="")]))
    covered |= codes(validate(policy_evidence=[make_evidence(status="draft")]))
    covered |= codes(
        validate(
            policy_status={"inconclusive": True, "reason": "weak_evidence"},
            policy_evidence=[],
        )
    )

    assert expected <= covered
