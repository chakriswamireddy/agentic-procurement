import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.models import ApprovalDecision


class ApprovalRepository:
    """PostgreSQL access for approval decisions. Callers commit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self, request_id: str, recommendation_version: int
    ) -> ApprovalDecision | None:
        statement = select(ApprovalDecision).where(
            ApprovalDecision.request_id == request_id,
            ApprovalDecision.recommendation_version == recommendation_version,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def create(
        self,
        *,
        request_id: str,
        approver_id: str,
        decision: str,
        reason: str | None,
        recommendation_version: int,
    ) -> ApprovalDecision:
        existing = await self.get(request_id, recommendation_version)
        if existing is not None:
            return existing

        record = ApprovalDecision(
            id=f"APR-{uuid.uuid4().hex}",
            request_id=request_id,
            approver_id=approver_id,
            decision=decision,
            reason=reason,
            recommendation_version=recommendation_version,
            decided_at=datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.flush()
        return record
