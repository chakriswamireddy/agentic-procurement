"""Unit tests for MCP client validation and error mapping (Phase 5.11)."""

import pytest
from app.mcp.client import MCPClient, MCPClientError, ToolResult


def test_validate_arguments_rejects_bad_payload() -> None:
    client = MCPClient()
    with pytest.raises(MCPClientError) as exc:
        client.validate_arguments("search_suppliers", {"category": "", "quantity": 0})
    assert exc.value.code == "invalid_arguments"


def test_validate_arguments_accepts_good_payload() -> None:
    client = MCPClient()
    parsed = client.validate_arguments(
        "search_suppliers", {"category": "electronics", "quantity": 10}
    )
    assert parsed.category == "electronics"


def test_create_purchase_request_schema_has_no_business_fields() -> None:
    from app.mcp.schemas import CreatePurchaseRequestInput

    fields = set(CreatePurchaseRequestInput.model_fields)
    assert fields == {"request_id", "idempotency_key"}
    for forbidden in ("supplier_id", "price", "quantity", "amount"):
        assert forbidden not in fields


@pytest.mark.asyncio
async def test_call_tool_unknown_returns_structured_error() -> None:
    from app.mcp.client import ToolInfo

    client = MCPClient()
    client._tools = {
        "search_suppliers": ToolInfo(
            name="search_suppliers", description="x", input_schema={"type": "object"}
        )
    }
    result = await client.call_tool("does_not_exist", {})
    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.error_code == "unknown_tool"


@pytest.mark.asyncio
async def test_call_tool_invalid_args_rejected_before_invoke() -> None:
    client = MCPClient()
    client._tools = {
        "search_suppliers": __import__("app.mcp.client", fromlist=["ToolInfo"]).ToolInfo(
            name="search_suppliers",
            description="x",
            input_schema={"type": "object"},
        )
    }
    result = await client.call_tool("search_suppliers", {"quantity": -1})
    assert result.ok is False
    assert result.error_code == "invalid_arguments"
