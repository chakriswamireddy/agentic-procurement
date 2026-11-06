import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.models import ExecutionRecord


class ExecutionRepository:
    """PostgreSQL access for execution records. Callers commit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_request(self, request_id: str) -> ExecutionRecord | None:
        statement = select(ExecutionRecord).where(
            ExecutionRecord.request_id == request_id
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> ExecutionRecord | None:
        statement = select(ExecutionRecord).where(
            ExecutionRecord.idempotency_key == key
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def upsert(
        self,
        *,
        request_id: str,
        idempotency_key: str,
        status: str,
        external_reference: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        record = await self.get_by_request(request_id)
        if record is None:
            record = ExecutionRecord(
                id=f"EXE-{uuid.uuid4().hex}",
                request_id=request_id,
                idempotency_key=idempotency_key,
                external_reference=external_reference,
                status=status,
                error_code=error_code,
            )
            self.session.add(record)
        else:
            record.idempotency_key = idempotency_key
            record.external_reference = external_reference
            record.status = status
            record.error_code = error_code
        await self.session.flush()
        return {
            "id": record.id,
            "request_id": record.request_id,
            "idempotency_key": record.idempotency_key,
            "external_reference": record.external_reference,
            "status": record.status,
            "error_code": record.error_code,
        }
