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


async def test_supplier_lookup_failure_alone_still_compares() -> None:
    """One failed branch must not mask the healthy policy branch."""
    dependencies = make_dependencies(supplier_error=TimeoutError("slow supplier"))
    graph = build_graph()
    state = make_state()
    config = {"configurable": {"thread_id": state["thread_id"]}}

    with use_dependencies(dependencies):
        result = await graph.ainvoke(state, config)

    codes = [error["code"] for error in result["errors"]]
    assert "supplier_lookup_failed" in codes
    # One failed branch must not mask the healthy policy branch: research still
    # reaches comparison, which reports the empty eligible set.
    assert result["status"] == "failed"
    assert result["failure_reason"] == "no_eligible_supplier"
    assert len(dependencies.policies.calls) == 1
