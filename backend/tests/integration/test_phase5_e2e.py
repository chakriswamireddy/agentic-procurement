"""End-to-end integration tests for Phase 5: Auth, POL-002 Approval, and MCP Execution."""

import pytest

pytestmark = pytest.mark.integration


async def test_auth_login_and_me_endpoints(live_client) -> None:
    # 1. Successful login
    login_resp = await live_client.post(
        "/api/v1/auth/login",
        json={"email": "user0002@example.test", "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    login_data = login_resp.json()
    assert "access_token" in login_data
    assert login_data["user"]["id"] == "USR0002"
    assert login_data["user"]["role"] == "requester"
    token = login_data["access_token"]

    # 2. Get profile with Bearer token
    me_resp = await live_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["id"] == "USR0002"
    assert me_data["role"] == "requester"

    # 3. Bad password returns 401
    bad_resp = await live_client.post(
        "/api/v1/auth/login",
        json={"email": "user0002@example.test", "password": "WrongPassword!"},
    )
    assert bad_resp.status_code == 401

    # 4. Unknown email returns 401
    unknown_resp = await live_client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.test", "password": "Password123!"},
    )
    assert unknown_resp.status_code == 401

    # 5. Missing token on /me returns 401
    unauth_resp = await live_client.get("/api/v1/auth/me")
    assert unauth_resp.status_code == 401


async def test_full_authenticated_procurement_lifecycle(live_client) -> None:
    # 1. Login as requester USR0002
    req_login = await live_client.post(
        "/api/v1/auth/login",
        json={"email": "user0002@example.test", "password": "Password123!"},
    )
    assert req_login.status_code == 200
    requester_token = req_login.json()["access_token"]

    # 2. Create procurement request using JWT (no requester_id in body)
    create_resp = await live_client.post(
        "/api/v1/procurement/requests",
        headers={"Authorization": f"Bearer {requester_token}"},
        json={
            "product_id": "PRD0001",
            "quantity": 100,
            "constraints": {},
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["requester_id"] == "USR0002"
    thread_id = created["thread_id"]
    assert created["status"] == "awaiting_approval"

    # 3. Self-approval attempt by requester MUST be rejected with 403 Forbidden
    self_approve_resp = await live_client.post(
        f"/api/v1/workflows/{thread_id}/approval",
        headers={"Authorization": f"Bearer {requester_token}"},
        json={"decision": "approved", "reason": "Self approving"},
    )
    assert self_approve_resp.status_code == 403, self_approve_resp.text
    assert "self_approval_prohibited" in self_approve_resp.text

    # 4. Login as approver USR0005
    app_login = await live_client.post(
        "/api/v1/auth/login",
        json={"email": "user0005@example.test", "password": "Password123!"},
    )
    assert app_login.status_code == 200
    approver_token = app_login.json()["access_token"]

    # 5. Approver executes valid approval
    approve_resp = await live_client.post(
        f"/api/v1/workflows/{thread_id}/approval",
        headers={"Authorization": f"Bearer {approver_token}"},
        json={
            "decision": "approved",
            "reason": "Verified and approved within policy budget",
        },
    )
    assert approve_resp.status_code == 200, approve_resp.text
    workflow_view = approve_resp.json()
    assert workflow_view["status"] == "executed"
    assert workflow_view["awaiting_approval"] is False

    # 6. Verify request record status is executed
    req_status_resp = await live_client.get(
        f"/api/v1/procurement/requests/{created['id']}",
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert req_status_resp.status_code == 200
    assert req_status_resp.json()["status"] == "executed"

    # 7. Duplicate resume returns 409 Conflict
    dup_resp = await live_client.post(
        f"/api/v1/workflows/{thread_id}/approval",
        headers={"Authorization": f"Bearer {approver_token}"},
        json={"decision": "approved", "reason": "Repeat approval"},
    )
    assert dup_resp.status_code == 409
