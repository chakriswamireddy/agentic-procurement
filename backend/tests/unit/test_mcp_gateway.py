"""Unit tests for Phase 5 MCP execution gateway."""

import pytest
from app.services.mcp_gateway import MCPExecutionGateway
from mcp.server.mcpserver.exceptions import ToolError


class FakeServer:
    """Minimal stand-in exposing the MCP server call_tool interface."""

    def __init__(self, *, fail: bool = False, payload: dict | None = None) -> None:
        self.fail = fail
        self.payload = payload or {}
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        if self.fail:
            raise RuntimeError("ERP connection refused")

        class Result:
            is_error = False
            structured_content = self.payload

        return Result()


@pytest.mark.asyncio
async def test_mcp_gateway_successful_order_execution() -> None:
    server = FakeServer(
        payload={
            "external_reference": "SIM-PRQ-12345-1",
            "status": "created",
            "request_id": "PRQ-12345",
            "idempotency_key": "PRQ-12345:1",
        }
    )
    gateway = MCPExecutionGateway(server=server)
    result = await gateway.create_purchase_request(
        request_id="PRQ-12345",
        idempotency_key="PRQ-12345:1",
        recommendation_version=1,
    )
    assert result.success is True
    assert result.external_reference == "SIM-PRQ-12345-1"
    assert result.error_code is None
    assert server.calls[0][0] == "create_purchase_request"


@pytest.mark.asyncio
async def test_mcp_gateway_handles_failing_server() -> None:
    gateway = MCPExecutionGateway(server=FakeServer(fail=True))
    result = await gateway.create_purchase_request(
        request_id="PRQ-12345",
        idempotency_key="PRQ-12345:1",
        recommendation_version=1,
    )
    assert result.success is False
    assert result.recoverable is True


@pytest.mark.asyncio
async def test_mcp_gateway_maps_terminal_tool_errors() -> None:
    class DenyingServer:
        async def call_tool(self, name: str, arguments: dict):
            raise ToolError("approval_required: no approval decision")

    gateway = MCPExecutionGateway(server=DenyingServer())
    result = await gateway.create_purchase_request(
        request_id="PRQ-12345",
        idempotency_key="PRQ-12345:1",
        recommendation_version=1,
    )
    assert result.success is False
    assert result.error_code == "approval_required"
    assert result.recoverable is False


@pytest.mark.asyncio
async def test_mcp_gateway_never_sends_business_values() -> None:
    server = FakeServer(payload={"external_reference": "SIM-X"})
    gateway = MCPExecutionGateway(server=server)
    await gateway.create_purchase_request(
        request_id="PRQ-1",
        idempotency_key="PRQ-1:1",
        recommendation_version=7,
    )
    _name, args = server.calls[0]
    assert set(args) == {"request_id", "idempotency_key"}
    assert "supplier_id" not in args
    assert "price" not in args
    assert "quantity" not in args
