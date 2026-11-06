"""Persistence of approval decisions.

Phase 3 trusts the resume caller for tests. Phase 5 adds authentication, authorization,
and a recommendation-version check at the API boundary.
"""

from typing import Any

from app.repositories.approval_repository import ApprovalRepository
from app.repositories.audit_repository import AuditRepository


class ApprovalService:
    def __init__(
        self,
        approvals: ApprovalRepository,
        audit: AuditRepository,
    ) -> None:
        self.approvals = approvals
        self.audit = audit

    async def record(
        self, *, state: dict[str, Any], approval: dict[str, Any]
    ) -> dict[str, Any]:
        recommendation = state.get("recommendation") or {}
        record = await self.approvals.create(
            request_id=state["request_id"],
            approver_id=approval["approver_id"],
            decision=approval["decision"],
            reason=approval.get("reason"),
            recommendation_version=int(recommendation["version"]),
        )
        await self.audit.append(
            event_type=f"approval_{approval['decision']}",
            request_id=state["request_id"],
            actor_id=approval["approver_id"],
            correlation_id=state.get("correlation_id"),
            details={
                "approval_id": record.id,
                "recommendation_version": recommendation["version"],
                "reason": approval.get("reason"),
            },
        )
        await self.approvals.session.commit()
        return {**approval, "id": record.id, "persisted": True}
