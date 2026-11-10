"""Integration: request/workflow APIs with real Postgres checkpointer (steps 3.8/3.13)."""

import pytest
from app.core.config import get_settings
from app.graph.builder import build_graph
from app.graph.checkpointer import checkpointer_context

pytestmark = pytest.mark.integration


async def _auth_headers(client, email: str, password: str = "Password123!") -> dict:
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _create_request(client, *, product_id: str = "PRD0001", quantity: int = 100) -> dict:
    headers = await _auth_headers(client, "user0002@example.test")
    response = await client.post(
        "/api/v1/procurement/requests",
        headers=headers,
        json={
            "product_id": product_id,
            "quantity": quantity,
            "constraints": {},
        },
    )
    assert response.status_code == 201, response.text
    assert response.headers["X-Workflow-Status"] == "awaiting_approval"
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


async def test_create_request_pauses_at_approval(live_client) -> None:
    body = await _create_request(live_client)

    assert body["id"].startswith("PRQ-")
    assert body["thread_id"] == body["id"]
    assert body["status"] == "awaiting_approval"
    assert body["recommendation"] is not None
    assert body["recommendation"]["supplier_id"] == "SUP0001"
    assert body["recommendation"]["version"] == 1
    assert body["recommendation"]["evidence_chunk_ids"]

    headers = await _auth_headers(live_client, "user0002@example.test")
    view = await live_client.get(
        f"/api/v1/workflows/{body['thread_id']}", headers=headers
    )
    assert view.status_code == 200
    workflow = view.json()
    assert workflow["status"] == "awaiting_approval"
    assert workflow["awaiting_approval"] is True
    assert workflow["current_node"] == "approval_interrupt"
    assert workflow["recommendation"]["supplier_id"] == "SUP0001"
    assert workflow["evidence_chunk_ids"]
    # Checkpoint internals must never leak into API responses.
    assert "checkpoint" not in workflow
    assert "configurable" not in workflow


async def test_get_request_and_workflow_unknown_ids_return_404(live_client) -> None:
    headers = await _auth_headers(live_client, "user0001@example.test")
    request = await live_client.get(
        "/api/v1/procurement/requests/PRQ-DOESNOTEXIST", headers=headers
    )
    assert request.status_code == 404

    workflow = await live_client.get(
        "/api/v1/workflows/PRQ-DOESNOTEXIST", headers=headers
    )
    assert workflow.status_code == 404


async def test_approve_flow_executes_purchase(live_client) -> None:
    body = await _create_request(live_client, product_id="PRD0003", quantity=50)
    thread_id = body["thread_id"]

    approver_headers = await _auth_headers(live_client, "user0005@example.test")
    resume = await live_client.post(
        f"/api/v1/workflows/{thread_id}/approval",
        headers=approver_headers,
        json={"decision": "approved", "reason": "within budget"},
    )
    assert resume.status_code == 200, resume.text
    workflow = resume.json()
    assert workflow["status"] == "executed"
    assert workflow["awaiting_approval"] is False

    request = await live_client.get(
        f"/api/v1/procurement/requests/{body['id']}", headers=approver_headers
    )
    assert request.status_code == 200
    record = request.json()
    assert record["status"] == "executed"
    assert record["recommendation"]["supplier_id"] == workflow["recommendation"]["supplier_id"]

    # A repeat resume while not awaiting approval must conflict, not re-execute.
    again = await live_client.post(
        f"/api/v1/workflows/{thread_id}/approval",
        headers=approver_headers,
        json={"decision": "approved", "reason": "repeat"},
    )
    assert again.status_code == 409


async def test_reject_flow_records_rejected(live_client) -> None:
    body = await _create_request(live_client, product_id="PRD0005", quantity=10)
    thread_id = body["thread_id"]

    approver_headers = await _auth_headers(live_client, "user0005@example.test")
    resume = await live_client.post(
        f"/api/v1/workflows/{thread_id}/approval",
        headers=approver_headers,
        json={"decision": "rejected", "reason": "cheaper source exists"},
    )
    assert resume.status_code == 200, resume.text
    workflow = resume.json()
    assert workflow["status"] == "rejected"

    request = await live_client.get(
        f"/api/v1/procurement/requests/{body['id']}", headers=approver_headers
    )
    assert request.json()["status"] == "rejected"


async def test_invalid_quantity_rejected_by_schema(live_client) -> None:
    headers = await _auth_headers(live_client, "user0002@example.test")
    response = await live_client.post(
        "/api/v1/procurement/requests",
        headers=headers,
        json={"product_id": "PRD0001", "quantity": 0, "constraints": {}},
    )
    assert response.status_code == 422


async def test_unknown_product_rejected(live_client) -> None:
    headers = await _auth_headers(live_client, "user0002@example.test")
    response = await live_client.post(
        "/api/v1/procurement/requests",
        headers=headers,
        json={"product_id": "PRD-NOPE", "quantity": 10, "constraints": {}},
    )
    assert response.status_code == 422


async def test_paused_workflow_readable_by_new_graph_instance(live_client) -> None:
    """Step 3.8: a second saver/graph instance reads the paused Postgres checkpoint."""
    body = await _create_request(live_client, product_id="PRD0002", quantity=25)
    thread_id = body["thread_id"]

    async with checkpointer_context(get_settings()) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})

    assert snapshot.values["status"] == "awaiting_approval"
    assert snapshot.values["recommendation"]["supplier_id"] == body["recommendation"]["supplier_id"]
    assert snapshot.next == ("approval_interrupt",)
