"""Graph-level validation and routing: invalid input, weak evidence, merge, bounds."""

import pytest
from app.graph.builder import build_graph
from app.graph.dependencies import use_dependencies
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from tests.graph.conftest import make_dependencies, make_evidence, make_state


async def test_invalid_quantity_routes_to_needs_info() -> None:
    dependencies = make_dependencies()
    graph = build_graph()
    state = make_state(request={**make_state()["request"], "quantity": 0})

    with use_dependencies(dependencies):
        result = await graph.ainvoke(
            state, {"configurable": {"thread_id": state["thread_id"]}}
        )

    assert result["status"] == "needs_info"
    assert result["failure_reason"] == "invalid_request"
    assert any(error["code"] == "invalid_quantity" for error in result["errors"])
    assert dependencies.suppliers.calls == []
    assert dependencies.policies.calls == []
    assert dependencies.results.calls[-1]["status"] == "needs_info"


async def test_weak_policy_evidence_routes_to_inconclusive() -> None:
    dependencies = make_dependencies(
        policy_result={
            "query": "query",
            "inconclusive": True,
            "reason": "weak_evidence",
            "evidence": [],
        }
    )
    graph = build_graph()
    state = make_state()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(
            state, {"configurable": {"thread_id": state["thread_id"]}}
        )

    assert result["status"] == "inconclusive"
    assert result["failure_reason"] == "policy_evidence_insufficient"
    assert "__interrupt__" not in result
    assert dependencies.approvals.calls == []
    # Phase 4 matrix: missing policy evidence stops before recommendation persistence.
    assert dependencies.recommendations.calls == []
    assert "comparison" not in result
    assert dependencies.results.calls[-1]["status"] == "inconclusive"


async def test_parallel_research_errors_merge_in_state() -> None:
    dependencies = make_dependencies(
        supplier_error=TimeoutError("supplier down"),
        policy_error=ConnectionError("policy down"),
    )
    graph = build_graph()
    state = make_state()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(
            state, {"configurable": {"thread_id": state["thread_id"]}}
        )

    nodes = {error.get("node") for error in result["errors"]}
    assert {"supplier_lookup", "policy_retrieval"} <= nodes
    assert len(result["errors"]) == 2
    assert result["status"] == "failed"
    assert result["failure_reason"] == "research_unavailable"
    assert dependencies.results.calls[-1]["status"] == "failed"


async def test_researcher_errors_reducer_merges_partial_updates() -> None:
    """Step 3.1 verify: two parallel writers must both survive the errors reducer."""

    async def branch_a(state) -> dict:
        return {"errors": [{"code": "from_a"}]}

    async def branch_b(state) -> dict:
        return {"errors": [{"code": "from_b"}]}

    import operator
    from typing import Annotated, Literal, TypedDict

    class MergeState(TypedDict):
        request_id: str
        thread_id: str
        user_id: str
        correlation_id: str
        as_of: str
        request: dict
        errors: Annotated[list[dict], operator.add]
        status: Literal["received"]

    builder = StateGraph(MergeState)
    builder.add_node("a", branch_a)
    builder.add_node("b", branch_b)
    builder.add_edge(START, "a")
    builder.add_edge(START, "b")
    builder.add_edge("a", END)
    builder.add_edge("b", END)
    graph = builder.compile(checkpointer=InMemorySaver())

    result = await graph.ainvoke(
        {"request_id": "r", "thread_id": "t", "user_id": "u", "correlation_id": "c",
         "as_of": "2026-01-15", "request": {}, "errors": [], "status": "received"},
        {"configurable": {"thread_id": "t"}},
    )

    assert result["errors"] == [{"code": "from_a"}, {"code": "from_b"}]


async def test_recursion_limit_stops_a_looping_graph() -> None:
    import operator
    from typing import Annotated, TypedDict

    class LoopState(TypedDict):
        count: Annotated[int, operator.add]

    async def loop(state: LoopState) -> dict:
        return {"count": 1}

    builder = StateGraph(LoopState)
    builder.add_node("loop", loop)
    builder.add_edge(START, "loop")
    builder.add_conditional_edges("loop", lambda _state: "loop", {"loop": "loop"})
    graph = builder.compile(checkpointer=InMemorySaver())

    with pytest.raises(GraphRecursionError):
        await graph.ainvoke(
            {"count": 0},
            {"configurable": {"thread_id": "loop-test"}, "recursion_limit": 5},
        )


async def test_policy_outage_alone_routes_to_inconclusive() -> None:
    """Failure drill 2: policy down must never reach approval."""
    dependencies = make_dependencies(policy_error=ConnectionError("policy down"))
    graph = build_graph()
    state = make_state()
    config = {"configurable": {"thread_id": state["thread_id"]}}

    with use_dependencies(dependencies):
        result = await graph.ainvoke(state, config)

    assert result["status"] == "inconclusive"
    assert result["failure_reason"] == "policy_unavailable"
    assert result["policy_status"]["reason"] == "dependency_unavailable"
    assert result["policy_status"]["inconclusive"] is True
    assert "__interrupt__" not in result
    assert dependencies.approvals.calls == []
    assert dependencies.recommendations.calls == []
    assert dependencies.results.calls[-1]["status"] == "inconclusive"


async def test_policy_evidence_shape_survives_into_state() -> None:
    evidence = make_evidence(chunk_id="chunk-abc")
    dependencies = make_dependencies(
        policy_result={
            "query": "q",
            "inconclusive": False,
            "reason": None,
            "evidence": [evidence],
        }
    )
    graph = build_graph()
    state = make_state()

    with use_dependencies(dependencies):
        result = await graph.ainvoke(
            state, {"configurable": {"thread_id": state["thread_id"]}}
        )

    assert result["policy_evidence"][0]["chunk_id"] == "chunk-abc"
    assert result["policy_status"]["inconclusive"] is False
