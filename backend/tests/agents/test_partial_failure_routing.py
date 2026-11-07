"""Partial-failure matrix at graph level: one test per row (step 4.9)."""

from app.graph.builder import build_graph
from app.graph.dependencies import use_dependencies
from tests.graph.conftest import make_dependencies, make_state

CONFIG = {"configurable": {"thread_id": "PRQ-FAIL0000001"}}


async def test_row1_healthy_research_reaches_approval() -> None:
    dependencies = make_dependencies()
    graph = build_graph()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(), CONFIG)

    assert result["status"] == "awaiting_approval"
    assert "__interrupt__" in result
    assert "failure_reason" not in result
    assert result["recommendation"]["supplier_id"] == "SUP0001"


async def test_row2_empty_candidates_fails_with_no_eligible_supplier() -> None:
    dependencies = make_dependencies(candidates=[])
    graph = build_graph()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(), CONFIG)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "no_eligible_supplier"
    assert result["comparison"]["eligible_count"] == 0


async def test_row3_supplier_transient_failure_fails_as_supplier_unavailable() -> None:
    dependencies = make_dependencies(supplier_error=TimeoutError("slow"))
    graph = build_graph()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(), CONFIG)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "supplier_unavailable"
    assert "comparison" not in result
    assert dependencies.results.calls[-1]["status"] == "failed"
    supplier_errors = [
        error for error in result["errors"] if error["node"] == "supplier_lookup"
    ]
    assert supplier_errors and supplier_errors[0]["transient"] is True


async def test_row4_inconclusive_policy_is_inconclusive() -> None:
    dependencies = make_dependencies(
        policy_result={
            "query": "q",
            "inconclusive": True,
            "reason": "weak_evidence",
            "evidence": [],
        }
    )
    graph = build_graph()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(), CONFIG)

    assert result["status"] == "inconclusive"
    assert result["failure_reason"] == "policy_evidence_insufficient"
    assert dependencies.recommendations.calls == []
    assert dependencies.approvals.calls == []


async def test_row5_policy_failure_is_inconclusive_policy_unavailable() -> None:
    dependencies = make_dependencies(policy_error=ConnectionError("qdrant down"))
    graph = build_graph()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(), CONFIG)

    assert result["status"] == "inconclusive"
    assert result["failure_reason"] == "policy_unavailable"
    assert result["policy_status"]["inconclusive"] is True
    assert dependencies.approvals.calls == []


async def test_row6_both_branches_down_is_research_unavailable() -> None:
    dependencies = make_dependencies(
        supplier_error=ConnectionError("db down"),
        policy_error=ConnectionError("qdrant down"),
    )
    graph = build_graph()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(), CONFIG)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "research_unavailable"
    nodes = {error["node"] for error in result["errors"]}
    assert {"supplier_lookup", "policy_retrieval"} <= nodes
    assert dependencies.results.calls[-1]["status"] == "failed"


async def test_row7_permanent_validation_failure_routes_to_specific_reason() -> None:
    """A tampered recommendation score must block approval with a specific reason."""
    dependencies = make_dependencies()
    original = dependencies.recommendations.prepare_and_persist

    async def tampered(**kwargs):
        recommendation = await original(**kwargs)
        recommendation["score"] = "1.00"
        return recommendation

    dependencies.recommendations.prepare_and_persist = tampered
    graph = build_graph()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(), CONFIG)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "validation_failed"
    assert any(issue["code"] == "score_mismatch" for issue in result["validation"]["issues"])
    assert "__interrupt__" not in result
    assert dependencies.approvals.calls == []


async def test_policy_failure_with_empty_candidates_still_fails_as_business_outcome() -> None:
    """Row 2 has priority: 'ok, empty | any' is no_eligible_supplier, not an outage."""
    dependencies = make_dependencies(
        candidates=[], policy_error=ConnectionError("qdrant down")
    )
    graph = build_graph()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(), CONFIG)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "no_eligible_supplier"
