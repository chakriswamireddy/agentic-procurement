"""Analysis and validation specialists: determinism and issue codes (steps 4.5/4.6)."""

from app.agents.analysis_specialist import AnalysisSpecialist
from app.agents.contracts import (
    ComparisonRequest,
    PermanentError,
    PolicyEvidence,
    ValidationRequest,
)
from app.agents.validation_specialist import ValidationSpecialist
from tests.graph.conftest import (
    AS_OF,
    FakeRecommendations,
    make_candidate,
    make_evidence,
    make_request,
)

EVIDENCE = (PolicyEvidence.from_dict(make_evidence()),)
POLICY_STATUS = {"query": "q", "inconclusive": False, "reason": None}


def make_comparison_request(**overrides) -> ComparisonRequest:
    request = overrides.pop("request", make_request())
    candidates = overrides.pop("candidates", [make_candidate()])
    return ComparisonRequest.from_state(
        request=request, candidates=candidates, as_of=AS_OF
    )


async def make_recommendation(comparison: dict) -> dict | None:
    fake = FakeRecommendations()
    return await fake.prepare_and_persist(
        request={"request_id": "PRQ-TEST00000001"},
        comparison=comparison,
        policy_evidence=[make_evidence()],
        policy_query="q",
        issues=[],
    )


async def test_analysis_is_deterministic_across_calls_and_instances() -> None:
    specialist = AnalysisSpecialist()
    other = AnalysisSpecialist()
    request = make_comparison_request()

    first = await specialist.compare(request)
    second = await specialist.compare(request)
    third = await other.compare(request)

    assert first.to_dict() == second.to_dict()
    assert first.to_dict() == third.to_dict()
    assert first.recommended is not None
    assert first.eligible_count == 1


async def test_analysis_maps_invalid_input_to_permanent_error() -> None:
    specialist = AnalysisSpecialist()
    request = ComparisonRequest.from_state(
        request=make_request(quantity=0),
        candidates=[make_candidate()],
        as_of=AS_OF,
    )

    try:
        await specialist.compare(request)
    except PermanentError as exc:
        assert exc.code == "invalid_comparison_input"
        assert exc.transient is False
    else:
        raise AssertionError("expected a PermanentError")


async def test_validation_accepts_a_complete_recommendation() -> None:
    comparison = await AnalysisSpecialist().compare(make_comparison_request())
    recommendation = await make_recommendation(comparison.to_dict())
    specialist = ValidationSpecialist()

    result = await specialist.validate(
        ValidationRequest(
            request=make_request(),
            comparison=comparison.to_dict(),
            recommendation=recommendation,
            policy_status=POLICY_STATUS,
            policy_evidence=EVIDENCE,
        )
    )

    assert result.sufficient is True
    assert result.issues == ()


async def test_validation_flags_score_mismatch() -> None:
    comparison = await AnalysisSpecialist().compare(make_comparison_request())
    recommendation = await make_recommendation(comparison.to_dict())
    assert recommendation is not None
    recommendation["score"] = "1.00"
    specialist = ValidationSpecialist()

    result = await specialist.validate(
        ValidationRequest(
            request=make_request(),
            comparison=comparison.to_dict(),
            recommendation=recommendation,
            policy_status=POLICY_STATUS,
            policy_evidence=EVIDENCE,
        )
    )

    codes = {issue["code"] for issue in result.issues}
    assert "score_mismatch" in codes
    assert result.sufficient is False


async def test_validation_flags_missing_request_info() -> None:
    specialist = ValidationSpecialist()

    result = await specialist.validate(
        ValidationRequest(
            request=make_request(quantity=0),
            comparison=None,
            recommendation=None,
            policy_status=POLICY_STATUS,
            policy_evidence=EVIDENCE,
        )
    )

    codes = {issue["code"] for issue in result.issues}
    assert "missing_request_info" in codes
    assert "no_eligible_supplier" in codes
    assert result.sufficient is False


async def test_validation_flags_weak_policy_evidence() -> None:
    comparison = await AnalysisSpecialist().compare(make_comparison_request())
    recommendation = await make_recommendation(comparison.to_dict())
    specialist = ValidationSpecialist()

    result = await specialist.validate(
        ValidationRequest(
            request=make_request(),
            comparison=comparison.to_dict(),
            recommendation=recommendation,
            policy_status={"query": "q", "inconclusive": True, "reason": "weak"},
            policy_evidence=(),
        )
    )

    codes = {issue["code"] for issue in result.issues}
    assert "weak_policy_evidence" in codes
    assert result.sufficient is False
