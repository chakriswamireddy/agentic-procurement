import logging

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"needs_info", "inconclusive", "failed", "rejected", "executed"}
RESEARCH_NODES = {"supplier_lookup", "policy_retrieval"}


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
    errors = state.get("errors") or []
    if status == "needs_info":
        return "invalid_request"
    if status == "inconclusive":
        return "policy_evidence_insufficient"
    if any(error.get("node") in RESEARCH_NODES for error in errors):
        return "research_unavailable"
    if status == "failed":
        return "workflow_failed"
    return None


async def record_result(state: ProcurementState) -> dict:
    dependencies = get_dependencies()
    status = _terminal_status(state)
    await dependencies.results.record_result(state=state, status=status)
    logger.info(
        "workflow finished",
        extra={
            "path": f"/workflows/{state['thread_id']}",
            "status": status,
            **dependencies.metrics.summary(),
        },
    )
    update: dict = {"status": status}
    failure_reason = _failure_reason(state, status)
    if failure_reason:
        update["failure_reason"] = failure_reason
    return update
