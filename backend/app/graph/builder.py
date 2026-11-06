"""Compile the procurement StateGraph once and reuse it per process."""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.graph.nodes.approval import approval_interrupt
from app.graph.nodes.compare_options import compare_options
from app.graph.nodes.execute import execute_tool
from app.graph.nodes.policy_retrieval import policy_retrieval
from app.graph.nodes.record_result import record_result
from app.graph.nodes.research_join import research_join
from app.graph.nodes.supplier_lookup import supplier_lookup
from app.graph.nodes.validate_recommendation import validate_recommendation
from app.graph.nodes.validate_request import validate_request
from app.graph.routing import (
    after_approval,
    after_execution,
    after_research,
    after_validate_request,
    after_validation,
)
from app.graph.state import ProcurementState

RESEARCH_RETRY = RetryPolicy(max_attempts=2)


def build_graph(*, checkpointer=None, name: str = "procurement_workflow"):
    builder = StateGraph(ProcurementState)

    builder.add_node("validate_request", validate_request)
    builder.add_node("supplier_lookup", supplier_lookup, retry_policy=RESEARCH_RETRY)
    builder.add_node("policy_retrieval", policy_retrieval, retry_policy=RESEARCH_RETRY)
    builder.add_node("research_join", research_join)
    builder.add_node("compare_options", compare_options)
    builder.add_node(
        "validate_recommendation", validate_recommendation
    )
    builder.add_node("approval_interrupt", approval_interrupt)
    builder.add_node("execute_tool", execute_tool)
    builder.add_node("record_result", record_result)

    builder.add_edge(START, "validate_request")
    builder.add_conditional_edges(
        "validate_request",
        after_validate_request,
        {
            "supplier_lookup": "supplier_lookup",
            "policy_retrieval": "policy_retrieval",
            "record_result": "record_result",
        },
    )
    builder.add_edge("supplier_lookup", "research_join")
    builder.add_edge("policy_retrieval", "research_join")
    builder.add_conditional_edges(
        "research_join",
        after_research,
        {
            "compare_options": "compare_options",
            "record_result": "record_result",
        },
    )
    builder.add_edge("compare_options", "validate_recommendation")
    builder.add_conditional_edges(
        "validate_recommendation",
        after_validation,
        {
            "approval_interrupt": "approval_interrupt",
            "record_result": "record_result",
        },
    )
    builder.add_conditional_edges(
        "approval_interrupt",
        after_approval,
        {
            "execute_tool": "execute_tool",
            "record_result": "record_result",
        },
    )
    builder.add_conditional_edges(
        "execute_tool",
        after_execution,
        {"record_result": "record_result"},
    )
    builder.add_edge("record_result", END)

    return builder.compile(
        checkpointer=checkpointer or InMemorySaver(),
        name=name,
    )
