import pytest

pytestmark = pytest.mark.integration


async def _auth_headers(
    client, email: str = "user0001@example.test", password: str = "Password123!"
) -> dict:
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}




async def test_policy_search_api_returns_evidence(live_client, ingested_qdrant) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get(
        "/api/v1/policies/search",
        headers=headers,
        params={"q": "approval threshold for laptop purchases", "limit": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["inconclusive"] is False
    assert body["evidence"]
    assert body["evidence"][0]["document_id"].startswith("POL-")
    assert body["evidence"][0]["source_path"].startswith("data/")


async def test_policy_search_api_abstains(live_client, ingested_qdrant) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get(
        "/api/v1/policies/search",
        headers=headers,
        params={"q": "How do I bake sourdough bread at home?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["inconclusive"] is True
    assert body["reason"] == "weak_evidence"
    assert body["evidence"] == []


async def test_document_registry_api(live_client, ingested_qdrant) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get(
        "/api/v1/documents", headers=headers, params={"status": "active"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 10
    assert all(item["status"] == "active" for item in body["items"])
