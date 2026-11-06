"""Pure routing functions. No I/O and no mutation."""

from typing import Literal

from app.graph.state import ProcurementState

Route = Literal[
    "supplier_lookup",
    "policy_retrieval",
    "compare_options",
    "approval_interrupt",
    "execute_tool",
    "record_result",
]


def after_validate_request(state: ProcurementState) -> list[str] | str:
    if state.get("status") == "needs_info":
        return "record_result"
    return ["supplier_lookup", "policy_retrieval"]


def after_research(state: ProcurementState) -> str:
    codes = {error.get("code") for error in state.get("errors") or []}
    if "supplier_lookup_failed" in codes and "policy_retrieval_failed" in codes:
        return "record_result"
    return "compare_options"


def after_validation(state: ProcurementState) -> str:
    validation = state.get("validation") or {}
    if validation.get("sufficient"):
        return "approval_interrupt"
    return "record_result"


def after_approval(state: ProcurementState) -> str:
    approval = state.get("approval") or {}
    if not approval.get("valid"):
        return "record_result"
    if approval.get("decision") == "approved":
        return "execute_tool"
    return "record_result"


def after_execution(state: ProcurementState) -> str:
    del state
    return "record_result"
