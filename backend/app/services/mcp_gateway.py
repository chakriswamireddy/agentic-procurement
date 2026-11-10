"""MCP-backed execution gateway implementing the ExecutionGateway protocol.

Production path can spawn a real stdio MCP client (``use_client=True``);
local/tests call the in-process server when a session factory is available.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.execution_service import ExecutionResult

logger = logging.getLogger(__name__)


class MCPExecutionGateway:
    """Execution gateway delegating purchase order creation to an MCP tool."""

    def __init__(self, server: Any | None = None, *, use_client: bool = False) -> None:
        if server is not None:
            self.server = server
        else:
            from app.mcp.server import mcp_server

            self.server = mcp_server
        self.use_client = use_client
        self._client: Any | None = None

    async def _get_client(self):
        if self._client is None:
            from app.mcp.client import MCPClient

            self._client = MCPClient()
            await self._client.connect()
        return self._client

    async def create_purchase_request(
        self,
        *,
        request_id: str,
        idempotency_key: str,
        recommendation_version: int,
    ) -> ExecutionResult:
        # Version is embedded in the derived key; the MCP server re-derives it
        # from the approval row and ignores caller-supplied business values.
        del recommendation_version
        try:
            if self.use_client:
                client = await self._get_client()
                result = await client.call_tool(
                    "create_purchase_request",
                    {
                        "request_id": request_id,
                        "idempotency_key": idempotency_key,
                    },
                )
                if not result.ok:
                    retryable = result.retryable
                    # Tool-level rejections (no approval / stale / conflict) are terminal.
                    terminal = result.error_code in {
                        "approval_required",
                        "approval_not_approved",
                        "request_not_approved",
                        "idempotency_conflict",
                        "request_not_found",
                        "no_recommendation",
                        "invalid_arguments",
                        "unknown_tool",
                    }
                    return ExecutionResult(
                        success=False,
                        error_code=result.error_code or "mcp_tool_execution_error",
                        recoverable=retryable and not terminal,
                    )
                external_ref = (result.data or {}).get(
                    "external_reference", f"SIM-{request_id}"
                )
                return ExecutionResult(success=True, external_reference=external_ref)

            raw = await self.server.call_tool(
                "create_purchase_request",
                {
                    "request_id": request_id,
                    "idempotency_key": idempotency_key,
                },
            )
            if getattr(raw, "is_error", False):
                return ExecutionResult(
                    success=False,
                    error_code="mcp_tool_execution_error",
                    recoverable=True,
                )

            external_ref = f"SIM-{request_id}"
            structured = getattr(raw, "structured_content", None)
            if isinstance(structured, dict):
                inner = structured.get("result", structured)
                if isinstance(inner, dict) and inner.get("external_reference"):
                    external_ref = inner["external_reference"]
                elif isinstance(inner, dict) and inner.get("code"):
                    return ExecutionResult(
                        success=False,
                        error_code=str(inner["code"]),
                        recoverable=bool(inner.get("retryable", False)),
                    )

            return ExecutionResult(success=True, external_reference=external_ref)
        except Exception as exc:
            message = str(exc)
            lower = message.lower()
            if "approval_required" in lower or "approval_not_approved" in lower:
                return ExecutionResult(
                    success=False, error_code="approval_required", recoverable=False
                )
            if "request_not_found" in lower or "request_not_approved" in lower:
                return ExecutionResult(
                    success=False, error_code="request_not_approved", recoverable=False
                )
            if "idempotency_conflict" in lower:
                return ExecutionResult(
                    success=False, error_code="idempotency_conflict", recoverable=False
                )
            if "no_recommendation" in lower:
                return ExecutionResult(
                    success=False, error_code="no_recommendation", recoverable=False
                )
            code = exc.__class__.__name__
            logger.warning(
                "mcp gateway failure",
                extra={"request_id": request_id, "error_code": code},
            )
            return ExecutionResult(
                success=False, error_code=code, recoverable=True
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
