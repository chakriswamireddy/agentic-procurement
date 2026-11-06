"""Terminal business-record updates for a workflow run."""

from typing import Any

from app.repositories.audit_repository import AuditRepository
from app.repositories.request_repository import RequestRepository


class ResultService:
    def __init__(
        self,
        requests: RequestRepository,
        audit: AuditRepository,
    ) -> None:
        self.requests = requests
        self.audit = audit

    async def record_result(self, *, state: dict[str, Any], status: str) -> None:
        changed = await self.requests.set_status(state["request_id"], status)
        if changed:
            await self.audit.append(
                event_type="workflow_status_changed",
                request_id=state["request_id"],
                actor_id=None,
                correlation_id=state.get("correlation_id"),
                details={"status": status},
            )
        await self.requests.session.commit()

    async def mark_status(
        self,
        *,
        state: dict[str, Any],
        status: str,
        event_type: str = "workflow_status_changed",
        details: dict[str, Any] | None = None,
    ) -> None:
        changed = await self.requests.set_status(state["request_id"], status)
        if changed:
            await self.audit.append(
                event_type=event_type,
                request_id=state["request_id"],
                actor_id=None,
                correlation_id=state.get("correlation_id"),
                details={"status": status, **(details or {})},
            )
        await self.requests.session.commit()
