import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _auth_headers(
    client, email: str = "user0001@example.test", password: str = "Password123!"
) -> dict:
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_list_suppliers_from_seeded_database(live_client: AsyncClient) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get("/api/v1/suppliers", headers=headers, params={"limit": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 100
    assert len(body["items"]) == 3
    assert body["limit"] == 3


async def test_list_suppliers_filters(live_client: AsyncClient) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get(
        "/api/v1/suppliers",
        headers=headers,
        params={"status": "active", "category": "electronics", "limit": 100},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"]
    assert all(item["status"] == "active" for item in body["items"])
    assert all(item["category"] == "electronics" for item in body["items"])


async def test_supplier_detail_includes_mongo_profile(live_client: AsyncClient) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get("/api/v1/suppliers/SUP0001", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "SUP0001"
    assert body["profile"] is not None
    assert body["profile"]["certifications"]
    assert body["quotations"]
    assert isinstance(body["quotations"][0]["unit_price"], str)


async def test_supplier_detail_missing(live_client: AsyncClient) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get("/api/v1/suppliers/SUP9999", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_sql_injection_attempt_is_treated_as_text(live_client: AsyncClient) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get(
        "/api/v1/suppliers",
        headers=headers,
        params={"q": "' OR 1=1 --"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_invalid_status_query(live_client: AsyncClient) -> None:
    headers = await _auth_headers(live_client)
    response = await live_client.get(
        "/api/v1/suppliers", headers=headers, params={"status": "deleted"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_readiness_reports_postgres(live_client: AsyncClient) -> None:
    response = await live_client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["postgres"]["status"] == "ok"
    assert body["checks"]["postgres"]["required"] is True


async def test_pagination_is_stable_and_has_no_duplicates(live_client: AsyncClient) -> None:
    headers = await _auth_headers(live_client)
    first = await live_client.get(
        "/api/v1/suppliers", headers=headers, params={"limit": 10, "offset": 0}
    )
    second = await live_client.get(
        "/api/v1/suppliers", headers=headers, params={"limit": 10, "offset": 10}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_ids = [item["id"] for item in first.json()["items"]]
    second_ids = [item["id"] for item in second.json()["items"]]
    assert len(first_ids) == 10
    assert len(second_ids) == 10
    assert set(first_ids).isdisjoint(second_ids)


async def test_suppliers_require_authentication(live_client: AsyncClient) -> None:
    response = await live_client.get("/api/v1/suppliers")
    assert response.status_code == 401
