import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.models import Recommendation


class RecommendationRepository:
    """PostgreSQL access for versioned recommendations. Callers commit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_version(self, request_id: str) -> int:
        statement = select(func.max(Recommendation.version)).where(
            Recommendation.request_id == request_id
        )
        current = (await self.session.execute(statement)).scalar_one_or_none()
        return int(current or 0) + 1

    async def create(
        self,
        *,
        request_id: str,
        supplier_id: str,
        score: Decimal,
        rationale: dict[str, Any],
        evidence: dict[str, Any],
        version: int,
    ) -> Recommendation:
        record = Recommendation(
            id=f"REC-{uuid.uuid4().hex}",
            request_id=request_id,
            supplier_id=supplier_id,
            score=score,
            rationale_json=rationale,
            evidence_json=evidence,
            version=version,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_version(
        self, request_id: str, version: int
    ) -> Recommendation | None:
        statement = select(Recommendation).where(
            Recommendation.request_id == request_id,
            Recommendation.version == version,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_latest(self, request_id: str) -> Recommendation | None:
        statement = (
            select(Recommendation)
            .where(Recommendation.request_id == request_id)
            .order_by(Recommendation.version.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()
