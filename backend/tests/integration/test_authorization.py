"""Authorization matrix tests (Phase 5.5 / 5.14)."""

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


async def test_requester_reads_own_request(live_client: AsyncClient) -> None:
    req_h = await _headers(live_client, "user0002@example.test")
    create = await live_client.post(
        "/api/v1/procurement/requests",
        headers=req_h,
        json={"product_id": "PRD0001", "quantity": 5, "constraints": {}},
    )
    assert create.status_code == 201
    request_id = create.json()["id"]

    own = await live_client.get(
        f"/api/v1/procurement/requests/{request_id}", headers=req_h
    )
    assert own.status_code == 200

    other_h = await _headers(live_client, "user0003@example.test")
    other = await live_client.get(
        f"/api/v1/procurement/requests/{request_id}", headers=other_h
    )
    # 404 avoids resource enumeration for foreign requester IDs.
    assert other.status_code == 404


async def test_requester_cannot_create_for_another_identity(
    live_client: AsyncClient,
) -> None:
    req_h = await _headers(live_client, "user0002@example.test")
    create = await live_client.post(
        "/api/v1/procurement/requests",
        headers=req_h,
        json={
            "product_id": "PRD0001",
            "quantity": 5,
            "constraints": {},
            "requester_id": "USR0001",
        },
    )
    assert create.status_code == 201
    assert create.json()["requester_id"] == "USR0002"


async def test_requester_cannot_approve(live_client: AsyncClient) -> None:
    req_h = await _headers(live_client, "user0002@example.test")
    create = await live_client.post(
        "/api/v1/procurement/requests",
        headers=req_h,
        json={"product_id": "PRD0001", "quantity": 5, "constraints": {}},
    )
    thread_id = create.json()["thread_id"]

    approve = await live_client.post(
        f"/api/v1/workflows/{thread_id}/approval",
        headers=req_h,
        json={"decision": "approved", "reason": "let me"},
    )
    assert approve.status_code == 403
    assert "self_approval_prohibited" in approve.text


async def test_auditor_write_denied(live_client: AsyncClient) -> None:
    aud_h = await _headers(live_client, "user0015@example.test")
    create = await live_client.post(
        "/api/v1/procurement/requests",
        headers=aud_h,
        json={"product_id": "PRD0001", "quantity": 5, "constraints": {}},
    )
    assert create.status_code == 403

    upload = await live_client.post(
        "/api/v1/documents",
        headers=aud_h,
        files={"file": ("x.md", b"# x", "text/markdown")},
    )
    assert upload.status_code == 403


async def test_document_upload_admin_only(live_client: AsyncClient) -> None:
    req_h = await _headers(live_client, "user0002@example.test")
    denied = await live_client.post(
        "/api/v1/documents",
        headers=req_h,
        files={"file": ("x.md", b"# x", "text/markdown")},
    )
    assert denied.status_code == 403

    admin_h = await _headers(live_client, "user0001@example.test")
    allowed = await live_client.post(
        "/api/v1/documents",
        headers=admin_h,
        files={
            "file": (
                "phase5-authz.md",
                (
                    b"---\n"
                    b"document_id: POL-900\n"
                    b"title: Phase 5 Authorization\n"
                    b"version: 1.0.0\n"
                    b"status: draft\n"
                    b"classification: internal\n"
                    b"effective_from: 2026-01-01\n"
                    b"---\n\n"
                    b"# Phase 5\n\nAdmin-only uploads for Phase 5.\n"
                ),
                "text/markdown",
            )
        },
    )
    assert allowed.status_code == 201, allowed.text


async def test_admin_cannot_approve_own_request(live_client: AsyncClient) -> None:
    admin_h = await _headers(live_client, "user0001@example.test")
    create = await live_client.post(
        "/api/v1/procurement/requests",
        headers=admin_h,
        json={"product_id": "PRD0001", "quantity": 5, "constraints": {}},
    )
    assert create.status_code == 201
    thread_id = create.json()["thread_id"]

    approve = await live_client.post(
        f"/api/v1/workflows/{thread_id}/approval",
        headers=admin_h,
        json={"decision": "approved", "reason": "self"},
    )
    assert approve.status_code == 403
    assert "self_approval_prohibited" in approve.text
