import pytest
import pytest_asyncio
from app.api.deps import get_current_user, get_current_user_optional, get_supplier_service
from app.core.errors import NotFoundError
from app.schemas.auth import AuthenticatedUser
from app.schemas.supplier import (
    QuotationSummary,
    SupplierDetail,
    SupplierList,
    SupplierProfile,
    SupplierRead,
)
from httpx import ASGITransport, AsyncClient


def _as_user(user_id="USR0001", role="admin", email="user0001@example.test"):
    user = AuthenticatedUser(id=user_id, email=email, role=role)
    return {
        get_current_user: (lambda u=user: u),
        get_current_user_optional: (lambda u=user: u),
    }



class StubSupplierService:
    def __init__(self, profile_store_available: bool = True) -> None:
        self.list_kwargs: dict = {}
        self.profile_store_available = profile_store_available

    async def list_suppliers(self, **kwargs) -> SupplierList:
        self.list_kwargs = kwargs
        item = SupplierRead(
            id="SUP0001",
            name="Apex Components Pvt Ltd",
            category="electronics",
            location="IN-TG",
            status="active",
        )
        return SupplierList(
            items=[item],
            total=1,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
        )

    async def get_supplier(self, supplier_id: str) -> SupplierDetail:
        if supplier_id == "SUP9999":
            raise NotFoundError(f"supplier {supplier_id} not found")
        if supplier_id == "BOOM":
            raise RuntimeError("deliberate failure drill")

        return SupplierDetail(
            id=supplier_id,
            name="Apex Components Pvt Ltd",
            category="electronics",
            location="IN-TG",
            status="active",
            profile=(
                SupplierProfile(supplier_type="electronics")
                if self.profile_store_available
                else None
            ),
            quotations=[
                QuotationSummary(
                    id="QTN00001",
                    product_id="PRD0001",
                    unit_price="61334.00",
                    currency="INR",
                    available_quantity=200,
                    delivery_days=20,
                    valid_until="2026-04-01",
                )
            ],
            profile_store_available=self.profile_store_available,
        )


@pytest_asyncio.fixture
async def stub_client(application, request):
    availability = getattr(request, "param", True)
    service = StubSupplierService(profile_store_available=availability)
    application.dependency_overrides[get_supplier_service] = lambda: service
    application.dependency_overrides.update(_as_user())
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    application.dependency_overrides.clear()


async def test_list_suppliers_defaults(stub_client: AsyncClient) -> None:
    response = await stub_client.get("/api/v1/suppliers")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["items"][0]["id"] == "SUP0001"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("limit", [0, 101])
async def test_list_suppliers_rejects_invalid_limit(
    stub_client: AsyncClient, limit: int
) -> None:
    response = await stub_client.get("/api/v1/suppliers", params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_list_suppliers_rejects_unknown_status(stub_client: AsyncClient) -> None:
    response = await stub_client.get("/api/v1/suppliers", params={"status": "deleted"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_supplier_detail_found(stub_client: AsyncClient) -> None:
    response = await stub_client.get("/api/v1/suppliers/SUP0001")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "SUP0001"
    assert body["profile"]["supplier_type"] == "electronics"
    assert body["quotations"][0]["unit_price"] == "61334.00"
    assert response.headers["cache-control"] == "no-store"


async def test_supplier_detail_missing_uses_envelope(stub_client: AsyncClient) -> None:
    response = await stub_client.get("/api/v1/suppliers/SUP9999")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["correlation_id"] == response.headers["x-request-id"]


async def test_unknown_route_uses_envelope(stub_client: AsyncClient) -> None:
    response = await stub_client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_request_id_is_echoed(stub_client: AsyncClient) -> None:
    response = await stub_client.get(
        "/health/live",
        headers={"X-Request-ID": "test-123"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-123"


async def test_invalid_request_id_is_replaced(stub_client: AsyncClient) -> None:
    response = await stub_client.get(
        "/health/live",
        headers={"X-Request-ID": "x" * 500},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "x" * 500


@pytest.mark.parametrize("stub_client", [False], indirect=True)
async def test_profile_unavailable_sets_warning_header(stub_client: AsyncClient) -> None:
    response = await stub_client.get("/api/v1/suppliers/SUP0001")

    assert response.status_code == 200
    assert response.json()["profile"] is None
    assert response.headers["x-profile-status"] == "unavailable"


async def test_health_live_does_not_need_dependencies(api_client: AsyncClient) -> None:
    response = await api_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unhandled_exception_returns_generic_500(stub_client: AsyncClient) -> None:
    response = await stub_client.get("/api/v1/suppliers/BOOM")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["message"] == "internal server error"
    assert "deliberate failure drill" not in response.text
    assert error["correlation_id"] == response.headers["x-request-id"]
