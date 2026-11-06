"""Approval interrupt: approve, reject, and invalid resume paths."""

from app.graph.builder import build_graph
from app.graph.dependencies import use_dependencies
from langgraph.types import Command
from tests.graph.conftest import make_dependencies, make_state

APPROVE = {"decision": "approved", "approver_id": "USR0001", "reason": "looks good"}
REJECT = {"decision": "rejected", "approver_id": "USR0001", "reason": "too expensive"}


async def _pause_at_approval(dependencies, graph, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    with use_dependencies(dependencies):
        result = await graph.ainvoke(make_state(thread_id=thread_id), config)
    assert "__interrupt__" in result
    return config


async def test_interrupt_pauses_with_status_awaiting_approval() -> None:
    dependencies = make_dependencies()
    graph = build_graph()
    config = await _pause_at_approval(dependencies, graph, "PRQ-INT00000001")

    snapshot = await graph.aget_state(config)
    assert snapshot.values["status"] == "awaiting_approval"
    assert snapshot.values["recommendation"]["supplier_id"] == "SUP0001"
    assert snapshot.next == ("approval_interrupt",)
    assert dependencies.approvals.calls == []
    assert dependencies.execution.calls == []


async def test_resume_approved_reaches_executed() -> None:
    dependencies = make_dependencies()
    graph = build_graph()
    thread_id = "PRQ-INT00000002"
    config = await _pause_at_approval(dependencies, graph, thread_id)

    with use_dependencies(dependencies):
        result = await graph.ainvoke(Command(resume=APPROVE), config)

    assert result["status"] == "executed"
    assert result["approval"]["decision"] == "approved"
    assert result["approval"]["valid"] is True
    assert len(dependencies.approvals.calls) == 1
    assert len(dependencies.execution.calls) == 1
    assert dependencies.results.calls[-1]["status"] == "executed"


async def test_resume_rejected_records_rejected_without_execution() -> None:
    dependencies = make_dependencies()
    graph = build_graph()
    thread_id = "PRQ-INT00000003"
    config = await _pause_at_approval(dependencies, graph, thread_id)

    with use_dependencies(dependencies):
        result = await graph.ainvoke(Command(resume=REJECT), config)

    assert result["status"] == "rejected"
    assert result["approval"]["decision"] == "rejected"
    assert dependencies.execution.calls == []
    assert len(dependencies.approvals.calls) == 1
    assert dependencies.results.calls[-1]["status"] == "rejected"


async def test_invalid_resume_decision_fails_safely() -> None:
    dependencies = make_dependencies()
    graph = build_graph()
    thread_id = "PRQ-INT00000004"
    config = await _pause_at_approval(dependencies, graph, thread_id)

    with use_dependencies(dependencies):
        result = await graph.ainvoke(
            Command(resume={"decision": "maybe", "approver_id": "USR0001"}), config
        )

    assert result["status"] == "failed"
    assert result["failure_reason"] == "invalid_approval"
    assert any(error["code"] == "invalid_approval" for error in result["errors"])
    assert dependencies.execution.calls == []
    assert dependencies.approvals.calls == []
    assert dependencies.results.calls[-1]["status"] == "failed"


async def test_resume_without_approver_fails_safely() -> None:
    dependencies = make_dependencies()
    graph = build_graph()
    thread_id = "PRQ-INT00000005"
    config = await _pause_at_approval(dependencies, graph, thread_id)

    with use_dependencies(dependencies):
        result = await graph.ainvoke(Command(resume={"decision": "approved"}), config)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "invalid_approval"
    assert dependencies.execution.calls == []


async def test_execution_failure_keeps_recoverable_state() -> None:
    dependencies = make_dependencies(execution_error=RuntimeError("gateway down"))
    graph = build_graph()
    thread_id = "PRQ-INT00000006"
    config = await _pause_at_approval(dependencies, graph, thread_id)

    with use_dependencies(dependencies):
        result = await graph.ainvoke(Command(resume=APPROVE), config)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "execution_failed"
    assert result["execution"]["recoverable"] is True
    assert result["approval"]["decision"] == "approved"
    assert dependencies.results.calls[-1]["status"] == "failed"
