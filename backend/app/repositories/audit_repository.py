import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.models import AuditEvent


class AuditRepository:
    """Append-only audit trail. Callers own the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        *,
        event_type: str,
        request_id: str | None = None,
        actor_id: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str:
        event = AuditEvent(
            id=f"AUD-{uuid.uuid4().hex}",
            actor_id=actor_id,
            request_id=request_id,
            event_type=event_type,
            details_json=details or {},
            correlation_id=correlation_id,
        )
        self.session.add(event)
        await self.session.flush()
        return event.id
