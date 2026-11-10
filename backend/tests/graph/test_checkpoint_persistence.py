"""Checkpoint persistence: a fresh graph instance reads and resumes paused state."""

from app.graph.builder import build_graph
from app.graph.dependencies import use_dependencies
from langgraph.checkpoint.memory import InMemorySaver
from tests.graph.conftest import make_dependencies, make_state


async def test_new_graph_instance_reads_paused_state() -> None:
    checkpointer = InMemorySaver()
    thread_id = "PRQ-CHK00000001"
    config = {"configurable": {"thread_id": thread_id}}
    state = make_state(thread_id=thread_id)

    first = make_dependencies()
    graph_one = build_graph(checkpointer=checkpointer)
    with use_dependencies(first):
        paused = await graph_one.ainvoke(state, config)
    assert "__interrupt__" in paused

    # Simulate a process restart: brand-new compiled graph, same checkpointer.
    second = make_dependencies()
    graph_two = build_graph(checkpointer=checkpointer)
    snapshot = await graph_two.aget_state(config)

    assert snapshot.values["status"] == "awaiting_approval"
    assert snapshot.values["recommendation"]["supplier_id"] == "SUP0001"
    assert snapshot.values["recommendation"]["persisted"] is True
    assert snapshot.next == ("approval_interrupt",)
    assert second.approvals.calls == []


async def test_new_graph_instance_can_resume_paused_state() -> None:
    from langgraph.types import Command

    checkpointer = InMemorySaver()
    thread_id = "PRQ-CHK00000002"
    config = {"configurable": {"thread_id": thread_id}}
    state = make_state(thread_id=thread_id)

    graph_one = build_graph(checkpointer=checkpointer)
    with use_dependencies(make_dependencies()):
        await graph_one.ainvoke(state, config)

    graph_two = build_graph(checkpointer=checkpointer)
    resume_deps = make_dependencies()
    with use_dependencies(resume_deps):
        result = await graph_two.ainvoke(
            Command(resume={"decision": "approved", "approver_id": "USR0001"}),
            config,
        )

    assert result["status"] == "executed"
    assert len(resume_deps.execution.calls) == 1


async def test_checkpoint_history_records_each_step() -> None:
    checkpointer = InMemorySaver()
    thread_id = "PRQ-CHK00000003"
    config = {"configurable": {"thread_id": thread_id}}

    graph = build_graph(checkpointer=checkpointer)
    with use_dependencies(make_dependencies()):
        await graph.ainvoke(make_state(thread_id=thread_id), config)

    history = [entry async for entry in graph.aget_state_history(config)]
    # At least: initial checkpoint, post-research, post-validation, paused interrupt.
    assert len(history) >= 4
    newest = history[0]
    assert newest.values["status"] == "awaiting_approval"


async def test_thread_ids_isolate_workflows() -> None:
    checkpointer = InMemorySaver()
    graph = build_graph(checkpointer=checkpointer)

    with use_dependencies(make_dependencies()):
        await graph.ainvoke(
            make_state(thread_id="PRQ-ISO00000001", request_id="PRQ-ISO00000001"),
            {"configurable": {"thread_id": "PRQ-ISO00000001"}},
        )
        other = await graph.aget_state({"configurable": {"thread_id": "PRQ-ISO00000002"}})

    assert other.values == {}
    assert other.next == ()


async def test_checkpointer_connection_failure_is_clear() -> None:
    """Failure drill 3: an unreachable checkpointer must fail loudly at startup."""
    import pytest
    from app.core.config import Settings
    from app.graph.checkpointer import checkpointer_context

    settings = Settings(
        database_url="postgresql+asyncpg://procurement:procurement@127.0.0.1:1/procurement",
        mongodb_url="mongodb://127.0.0.1:1/procurement",
        jwt_secret="test-secret-0123456789abcdef01234567",
        checkpointer_database_url="postgresql://procurement:procurement@127.0.0.1:1/procurement",
    )

    with pytest.raises(Exception) as excinfo:
        async with checkpointer_context(settings):
            pass

    message = str(excinfo.value).lower()
    assert "refused" in message or "connect" in message or "connection" in message
