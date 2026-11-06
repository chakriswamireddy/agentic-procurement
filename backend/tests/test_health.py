from httpx import AsyncClient


async def test_liveness_returns_ok(api_client: AsyncClient) -> None:
    response = await api_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_liveness_echoes_request_id(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/health/live",
        headers={"X-Request-ID": "health-check-1"},
    )

    assert response.headers["x-request-id"] == "health-check-1"
