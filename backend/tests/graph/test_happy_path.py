"""Happy path: parallel research, comparison, validation, approval interrupt."""

import json

from app.graph.builder import build_graph
from app.graph.dependencies import use_dependencies
from tests.graph.conftest import make_dependencies, make_state


async def test_happy_path_pauses_at_approval_interrupt() -> None:
    dependencies = make_dependencies()
    graph = build_graph()
    state = make_state()
    config = {"configurable": {"thread_id": state["thread_id"]}}

    with use_dependencies(dependencies):
        result = await graph.ainvoke(state, config)

    assert "__interrupt__" in result
    assert result["status"] == "awaiting_approval"
    assert result["recommendation"]["persisted"] is True
    assert result["recommendation"]["supplier_id"] == "SUP0001"
    assert result["comparison"]["eligible_count"] == 1

    payload = result["__interrupt__"][0].value
    assert payload["request_id"] == state["request_id"]
    assert payload["recommendation_version"] == 1
    assert payload["supplier_id"] == "SUP0001"
    assert payload["evidence_chunk_ids"] == ["chunk-0001"]

    assert len(dependencies.recommendations.calls) == 1
    assert dependencies.approvals.calls == []
    assert dependencies.execution.calls == []
    assert dependencies.results.calls == []


async def test_parallel_research_both_branches_run() -> None:
    dependencies = make_dependencies()
    graph = build_graph()
    state = make_state()
    config = {"configurable": {"thread_id": state["thread_id"]}}

    with use_dependencies(dependencies):
        await graph.ainvoke(state, config)

    assert len(dependencies.suppliers.calls) == 1
    assert len(dependencies.policies.calls) == 1
    assert dependencies.suppliers.calls[0]["as_of"] == state["as_of"]
    assert dependencies.policies.calls[0]["as_of"] == state["as_of"]


async def test_same_inputs_produce_identical_scores_across_runs() -> None:
    first_deps = make_dependencies()
    second_deps = make_dependencies()
    graph = build_graph()

    outputs = []
    for index, dependencies in enumerate((first_deps, second_deps), start=1):
        state = make_state(thread_id=f"PRQ-DET{index:08d}", request_id=f"PRQ-DET{index:08d}")
        with use_dependencies(dependencies):
            result = await graph.ainvoke(
                state, {"configurable": {"thread_id": state["thread_id"]}}
            )
        outputs.append(
            {
                "score": result["recommendation"]["score"],
                "total_cost": result["recommendation"]["total_cost"],
                "supplier_id": result["recommendation"]["supplier_id"],
                "comparison": result["comparison"],
            }
        )

    assert outputs[0]["score"] == outputs[1]["score"]
    assert outputs[0]["total_cost"] == outputs[1]["total_cost"]
    assert outputs[0]["supplier_id"] == outputs[1]["supplier_id"]
    assert json.dumps(outputs[0]["comparison"], sort_keys=True) == json.dumps(
        outputs[1]["comparison"], sort_keys=True
    )
