import logging
from typing import Any

from langgraph.types import interrupt

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)

VALID_DECISIONS = {"approved", "rejected"}


def _interrupt_payload(state: ProcurementState) -> dict[str, Any]:
    recommendation = state.get("recommendation") or {}
    evidence = state.get("policy_evidence") or []
    return {
        "request_id": state["request_id"],
        "recommendation_version": recommendation.get("version"),
        "supplier_id": recommendation.get("supplier_id"),
        "supplier_name": recommendation.get("supplier_name"),
        "score": recommendation.get("score"),
        "total_cost": recommendation.get("total_cost"),
        "evidence_chunk_ids": [item.get("chunk_id") for item in evidence],
    }


def _normalize_decision(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    decision = value.get("decision")
    approver_id = value.get("approver_id")
    reason = value.get("reason")
    if decision not in VALID_DECISIONS:
        return None
    if not isinstance(approver_id, str) or not approver_id.strip():
        return None
    if reason is not None and not isinstance(reason, str):
        return None
    return {
        "decision": decision,
        "approver_id": approver_id.strip(),
        "reason": reason.strip() if isinstance(reason, str) and reason.strip() else None,
    }


async def approval_interrupt(state: ProcurementState) -> dict:
    raw_decision = interrupt(_interrupt_payload(state))
    decision = _normalize_decision(raw_decision)
    if decision is None:
        logger.warning(
            "invalid approval decision",
            extra={"path": f"/workflows/{state['thread_id']}"},
        )
        return {
            "approval": {"valid": False},
            "status": "failed",
            "failure_reason": "invalid_approval",
            "errors": [
                {
                    "code": "invalid_approval",
                    "message": "approval decision must be approved or rejected with an approver",
                    "node": "approval_interrupt",
                }
            ],
        }

    approval = {**decision, "valid": True}
    try:
        stored = await get_dependencies().approvals.record(
            state=state, approval=approval
        )
    except Exception as exc:
        logger.exception(
            "approval persistence failed",
            extra={"path": f"/workflows/{state['thread_id']}"},
        )
        return {
            "approval": {**approval, "valid": False, "persisted": False},
            "status": "failed",
            "failure_reason": "approval_persistence_failed",
            "errors": [
                {
                    "code": "approval_persistence_failed",
                    "message": exc.__class__.__name__,
                    "node": "approval_interrupt",
                }
            ],
        }

    return {
        "approval": stored,
        "status": "approved" if decision["decision"] == "approved" else "rejected",
    }
