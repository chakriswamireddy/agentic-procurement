"""No eligible supplier: structured failure, no approval interrupt."""

from app.graph.builder import build_graph
from app.graph.dependencies import use_dependencies
from tests.graph.conftest import make_candidate, make_dependencies, make_state


async def test_empty_candidate_list_fails_without_interrupt() -> None:
    dependencies = make_dependencies(candidates=[])
    graph = build_graph()
    state = make_state()
    config = {"configurable": {"thread_id": state["thread_id"]}}

    with use_dependencies(dependencies):
        result = await graph.ainvoke(state, config)

    assert "__interrupt__" not in result
    assert result["status"] == "failed"
    assert result["failure_reason"] == "no_eligible_supplier"
    assert result["comparison"]["reason"] == "no_eligible_supplier"
    assert result["comparison"]["eligible_count"] == 0
    assert result.get("recommendation") is None
    assert dependencies.approvals.calls == []
    assert dependencies.execution.calls == []
    assert dependencies.results.calls[-1]["status"] == "failed"


async def test_all_candidates_excluded_records_reasons() -> None:
    expired = make_candidate(supplier_id="SUP0001", valid_until="2026-01-01")
    inactive = make_candidate(
        supplier_id="SUP0002", quotation_id="QTN00002", supplier_status="inactive"
    )
    dependencies = make_dependencies(candidates=[expired, inactive])
    graph = build_graph()
    state = make_state()
    config = {"configurable": {"thread_id": state["thread_id"]}}

    with use_dependencies(dependencies):
        result = await graph.ainvoke(state, config)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "no_eligible_supplier"
    reasons = {item["supplier_id"]: item["reasons"] for item in result["comparison"]["excluded"]}
    assert reasons["SUP0001"] == ["expired_quotation"]
    assert reasons["SUP0002"] == ["inactive_supplier"]
    assert dependencies.recommendations.calls == []


async def test_supplier_outage_alone_routes_to_supplier_unavailable() -> None:
    """Phase 4 matrix: supplier down (policy healthy) is an operational failure."""
    dependencies = make_dependencies(supplier_error=TimeoutError("slow supplier"))
    graph = build_graph()
    state = make_state()
    config = {"configurable": {"thread_id": state["thread_id"]}}

    with use_dependencies(dependencies):
        result = await graph.ainvoke(state, config)

    supplier_errors = [
        error for error in result["errors"] if error.get("node") == "supplier_lookup"
    ]
    assert supplier_errors
    assert supplier_errors[0]["code"] in {"supplier_db_unavailable", "supplier_timeout"}
    assert result["status"] == "failed"
    assert result["failure_reason"] == "supplier_unavailable"
    # The healthy policy branch still ran, but the workflow never compares.
    assert len(dependencies.policies.calls) == 1
    assert "comparison" not in result
    assert dependencies.results.calls[-1]["status"] == "failed"
