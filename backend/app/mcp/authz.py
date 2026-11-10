"""Independent approval checks enforced by the MCP server (Phase 5.10).

The MCP server never trusts the caller's claim that an approval exists.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.models import (
    ApprovalDecision,
    ExecutionRecord,
    ProcurementRequest,
    Recommendation,
)


@dataclass(frozen=True)
class ApprovalCheck:
    allowed: bool
    code: str
    message: str
    recommendation_version: int | None = None


async def verify_approval_for_execution(
    session: AsyncSession, *, request_id: str
) -> ApprovalCheck:
    """Require an approved decision bound to the current recommendation version."""
    request = await session.get(ProcurementRequest, request_id)
    if request is None:
        return ApprovalCheck(False, "request_not_found", "request does not exist")
    if request.status in ("rejected", "received", "failed"):
        return ApprovalCheck(
            False,
            "request_not_approved",
            f"request status {request.status} cannot create a purchase",
        )

    version_row = (
        await session.execute(
            select(Recommendation.version)
            .where(Recommendation.request_id == request_id)
            .order_by(Recommendation.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if version_row is None:
        return ApprovalCheck(False, "no_recommendation", "no recommendation available")
    version = int(version_row)

    approval = (
        await session.execute(
            select(ApprovalDecision).where(
                ApprovalDecision.request_id == request_id,
                ApprovalDecision.recommendation_version == version,
            )
        )
    ).scalar_one_or_none()
    if approval is None:
        return ApprovalCheck(
            False,
            "approval_required",
            "no approval decision for current recommendation version",
            version,
        )
    if approval.decision != "approved":
        return ApprovalCheck(
            False,
            "approval_not_approved",
            f"decision is {approval.decision}",
            version,
        )
    return ApprovalCheck(True, "ok", "approved", version)


async def find_existing_execution(
    session: AsyncSession, *, request_id: str, idempotency_key: str
) -> ExecutionRecord | None:
    by_key = (
        await session.execute(
            select(ExecutionRecord).where(
                ExecutionRecord.idempotency_key == idempotency_key
            )
        )
    ).scalar_one_or_none()
    if by_key is not None:
        return by_key
    return (
        await session.execute(
            select(ExecutionRecord).where(ExecutionRecord.request_id == request_id)
        )
    ).scalar_one_or_none()
