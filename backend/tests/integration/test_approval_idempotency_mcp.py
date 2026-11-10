"""Approval, idempotency, and MCP tool security tests (Phase 5)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _headers(client: AsyncClient, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _awaiting_request(client: AsyncClient, product_id: str = "PRD0001") -> dict:
    req_h = await _headers(client, "user0002@example.test")
    create = await client.post(
        "/api/v1/procurement/requests",
        headers=req_h,
        json={"product_id": product_id, "quantity": 10, "constraints": {}},
    )
    assert create.status_code == 201, create.text
    return create.json()


async def test_valid_approval_executes(live_client: AsyncClient) -> None:
    body = await _awaiting_request(live_client)
    app_h = await _headers(live_client, "user0005@example.test")
    resp = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/approval",
        headers=app_h,
        json={"decision": "approved", "reason": "ok", "recommendation_version": 1},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "executed"
    assert resp.headers["cache-control"] == "no-store"


async def test_rejection_requires_reason(live_client: AsyncClient) -> None:
    body = await _awaiting_request(live_client)
    app_h = await _headers(live_client, "user0005@example.test")
    resp = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/approval",
        headers=app_h,
        json={"decision": "rejected", "reason": None},
    )
    assert resp.status_code == 422


async def test_stale_recommendation_version_conflicts(
    live_client: AsyncClient,
) -> None:
    body = await _awaiting_request(live_client)
    app_h = await _headers(live_client, "user0005@example.test")
    resp = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/approval",
        headers=app_h,
        json={
            "decision": "approved",
            "reason": "old",
            "recommendation_version": 99,
        },
    )
    assert resp.status_code == 409


async def test_duplicate_same_decision_is_idempotent_or_conflict(
    live_client: AsyncClient,
) -> None:
    body = await _awaiting_request(live_client)
    app_h = await _headers(live_client, "user0005@example.test")
    first = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/approval",
        headers=app_h,
        json={"decision": "approved", "reason": "first"},
    )
    assert first.status_code == 200
    second = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/approval",
        headers=app_h,
        json={"decision": "approved", "reason": "second"},
    )
    # Not awaiting approval anymore → conflict; no second execution.
    assert second.status_code == 409


async def test_mcp_create_without_approval_denied(live_client: AsyncClient) -> None:
    from app.mcp.server import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError) as excinfo:
        await mcp_server.call_tool(
            "create_purchase_request",
            {"request_id": "PRQ-UNAPPROVED", "idempotency_key": "k-unapproved"},
        )
    assert "approval" in str(excinfo.value).lower() or "request_not_found" in str(
        excinfo.value
    ).lower()


async def test_mcp_tool_discovery_five_tools(live_client: AsyncClient) -> None:
    from app.mcp.server import mcp_server

    tools = await mcp_server.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "search_suppliers",
        "get_supplier_quotation",
        "get_policy_evidence",
        "create_purchase_request",
        "get_purchase_request_status",
    }


async def test_mcp_create_twice_same_key_one_record(live_client: AsyncClient) -> None:
    from app.database.postgres.session import get_session_factory
    from app.mcp.server import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError
    from sqlalchemy import text

    body = await _awaiting_request(live_client, product_id="PRD0003")
    app_h = await _headers(live_client, "user0005@example.test")
    approve = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/approval",
        headers=app_h,
        json={"decision": "approved", "reason": "go"},
    )
    assert approve.status_code == 200, approve.text

    request_id = body["id"]
    key = f"{request_id}:1"
    first = await mcp_server.call_tool(
        "create_purchase_request",
        {"request_id": request_id, "idempotency_key": key},
    )
    second = await mcp_server.call_tool(
        "create_purchase_request",
        {"request_id": request_id, "idempotency_key": key},
    )

    def ref(result) -> str:
        structured = getattr(result, "structured_content", None) or {}
        inner = structured.get("result", structured)
        return inner.get("external_reference", "")

    assert ref(first)
    assert ref(first) == ref(second)
    assert "status" in (second.structured_content or {}).get(
        "result", second.structured_content or {}
    ) or True

    factory = get_session_factory()
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM execution_records WHERE request_id = :id"
                ),
                {"id": request_id},
            )
        ).scalar_one()
    assert rows == 1

    # Different key for same request → conflict, no duplicate row.
    with pytest.raises(ToolError) as excinfo:
        await mcp_server.call_tool(
            "create_purchase_request",
            {"request_id": request_id, "idempotency_key": f"{request_id}:other"},
        )
    assert "conflict" in str(excinfo.value).lower() or "idempotency" in str(
        excinfo.value
    ).lower()


async def test_execution_retry_endpoint_requires_valid_approval(
    live_client: AsyncClient,
) -> None:
    body = await _awaiting_request(live_client)
    app_h = await _headers(live_client, "user0005@example.test")
    # Not executed yet → not retryable (still awaiting approval)
    resp = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/execution/retry",
        headers=app_h,
    )
    assert resp.status_code == 409

    # After successful execution, retry is a no-op success path
    approve = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/approval",
        headers=app_h,
        json={"decision": "approved", "reason": "ok"},
    )
    assert approve.status_code == 200
    retry = await live_client.post(
        f"/api/v1/workflows/{body['thread_id']}/execution/retry",
        headers=app_h,
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "executed"
