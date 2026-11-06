"""Execution gateway interface and Phase 3 fake implementation.

The fake never claims a real purchase. Phase 5 swaps it for the MCP tool while keeping
the same node/service interface.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from app.repositories.audit_repository import AuditRepository
from app.repositories.execution_repository import ExecutionRepository


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    external_reference: str | None = None
    error_code: str | None = None
    recoverable: bool = True


class ExecutionGateway(Protocol):
    async def create_purchase_request(
        self, *, request_id: str, idempotency_key: str, recommendation_version: int
    ) -> ExecutionResult: ...


class FakeExecutionGateway:
    """Deterministic local simulator used by tests and local demos."""

    async def create_purchase_request(
        self, *, request_id: str, idempotency_key: str, recommendation_version: int
    ) -> ExecutionResult:
        del idempotency_key
        return ExecutionResult(
            success=True,
            external_reference=f"SIM-{request_id}-{recommendation_version}",
        )


class ExecutionService:
    def __init__(
        self,
        gateway: ExecutionGateway,
        executions: ExecutionRepository,
        audit: AuditRepository,
    ) -> None:
        self.gateway = gateway
        self.executions = executions
        self.audit = audit

    async def execute(self, *, state: dict[str, Any]) -> dict[str, Any]:
        request_id = state["request_id"]
        recommendation = state["recommendation"]
        version = int(recommendation["version"])
        idempotency_key = f"{request_id}:{version}"

        existing = await self.executions.get_by_idempotency_key(idempotency_key)
        if existing is not None and existing.status == "succeeded":
            return {
                "success": True,
                "idempotency_key": idempotency_key,
                "external_reference": existing.external_reference,
                "recovered": True,
                "recoverable": False,
                "error_code": None,
            }

        try:
            result = await self.gateway.create_purchase_request(
                request_id=request_id,
                idempotency_key=idempotency_key,
                recommendation_version=version,
            )
        except Exception as exc:  # gateway failures must become recoverable state
            result = ExecutionResult(
                success=False,
                error_code=exc.__class__.__name__,
                recoverable=True,
            )

        record = await self.executions.upsert(
            request_id=request_id,
            idempotency_key=idempotency_key,
            status="succeeded" if result.success else "failed",
            external_reference=result.external_reference,
            error_code=result.error_code,
        )
        await self.audit.append(
            event_type="execution_succeeded" if result.success else "execution_failed",
            request_id=request_id,
            correlation_id=state.get("correlation_id"),
            details={
                "idempotency_key": idempotency_key,
                "recommendation_version": version,
                "external_reference": result.external_reference,
                "error_code": result.error_code,
            },
        )
        await self.executions.session.commit()
        return {
            "success": result.success,
            "idempotency_key": idempotency_key,
            "external_reference": result.external_reference,
            "error_code": result.error_code,
            "recoverable": result.recoverable,
            "recovered": False,
            "record_id": record["id"],
        }
