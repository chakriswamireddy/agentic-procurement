import logging

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"needs_info", "inconclusive", "failed", "rejected", "executed"}


def _terminal_status(state: ProcurementState) -> str:
    status = state.get("status")
    if status in TERMINAL_STATUSES:
        return status
    approval = state.get("approval") or {}
    if approval.get("valid") and approval.get("decision") == "rejected":
        return "rejected"
    execution = state.get("execution") or {}
    if execution.get("success"):
        return "executed"
    return "failed"


def _failure_reason(state: ProcurementState, status: str) -> str | None:
    existing = state.get("failure_reason")
    if existing:
        return existing
    codes = {error.get("code") for error in state.get("errors") or []}
    if status == "needs_info":
        return "invalid_request"
    if status == "inconclusive":
        return "weak_policy_evidence"
    if {"supplier_lookup_failed", "policy_retrieval_failed"} & codes:
        return "research_failed"
    if status == "failed":
        return "workflow_failed"
    return None


async def record_result(state: ProcurementState) -> dict:
    status = _terminal_status(state)
    await get_dependencies().results.record_result(state=state, status=status)
    logger.info(
        "workflow finished",
        extra={"path": f"/workflows/{state['thread_id']}", "status": status},
    )
    update: dict = {"status": status}
    failure_reason = _failure_reason(state, status)
    if failure_reason:
        update["failure_reason"] = failure_reason
    return update
