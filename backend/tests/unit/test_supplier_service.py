from types import SimpleNamespace

import pytest
from app.core.errors import DependencyUnavailableError, NotFoundError, ValidationError
from app.schemas.supplier import SupplierProfile
from app.services.supplier_service import SupplierService
from pymongo.errors import PyMongoError
from sqlalchemy.exc import OperationalError


def make_supplier(supplier_id: str = "SUP0001") -> SimpleNamespace:
    return SimpleNamespace(
        id=supplier_id,
        name="Apex Components Pvt Ltd",
        category="electronics",
        location="IN-TG",
        status="active",
        quotations=[
            SimpleNamespace(
                id="QTN00001",
                product_id="PRD0001",
                unit_price="61334.00",
                currency="INR",
                available_quantity=200,
                delivery_days=20,
                valid_until="2026-04-01",
            )
        ],
    )


class FakeSupplierRepository:
    def __init__(self, rows=None, supplier=None, error=None) -> None:
        self.rows = rows or []
        self.supplier = supplier
        self.error = error
        self.calls: list[dict] = []

    async def list_suppliers(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.rows, len(self.rows)

    async def get_supplier(self, supplier_id: str):
        if self.error is not None:
            raise self.error
        return self.supplier


class FakeProfileRepository:
    def __init__(self, profile=None, error=None) -> None:
        self.profile = profile
        self.error = error

    async def get_profile(self, supplier_id: str):
        if self.error is not None:
            raise self.error
        return self.profile


async def test_list_normalizes_filters() -> None:
    repository = FakeSupplierRepository(rows=[make_supplier()])
    service = SupplierService(repository, FakeProfileRepository())

    result = await service.list_suppliers(
        category=" Electronics ",
        status=" ACTIVE ",
        q=" Apex ",
        limit=10,
        offset=5,
    )

    assert repository.calls == [
        {
            "category": "electronics",
            "location": None,
            "status": "active",
            "q": "Apex",
            "limit": 10,
            "offset": 5,
        }
    ]
    assert result.total == 1
    assert result.items[0].id == "SUP0001"


async def test_list_rejects_unknown_status() -> None:
    service = SupplierService(FakeSupplierRepository(), FakeProfileRepository())

    with pytest.raises(ValidationError):
        await service.list_suppliers(status="deleted")


async def test_detail_missing_raises_not_found() -> None:
    service = SupplierService(FakeSupplierRepository(supplier=None), FakeProfileRepository())

    with pytest.raises(NotFoundError):
        await service.get_supplier("SUP9999")


async def test_detail_composes_profile_and_quotations() -> None:
    profile = SupplierProfile(
        supplier_type="electronics",
        certifications=["ISO9001"],
        compliance={"risk_level": "low"},
    )
    service = SupplierService(
        FakeSupplierRepository(supplier=make_supplier()),
        FakeProfileRepository(profile=profile),
    )

    detail = await service.get_supplier("SUP0001")

    assert detail.id == "SUP0001"
    assert detail.profile is not None
    assert detail.profile.certifications == ["ISO9001"]
    assert len(detail.quotations) == 1
    assert detail.profile_store_available is True


async def test_detail_degrades_when_mongo_is_down() -> None:
    service = SupplierService(
        FakeSupplierRepository(supplier=make_supplier()),
        FakeProfileRepository(error=PyMongoError("mongo down")),
    )

    detail = await service.get_supplier("SUP0001")

    assert detail.id == "SUP0001"
    assert detail.profile is None
    assert detail.profile_store_available is False


async def test_list_maps_connection_failure_to_503() -> None:
    error = OperationalError("SELECT 1", {}, ConnectionRefusedError())
    service = SupplierService(FakeSupplierRepository(error=error), FakeProfileRepository())

    with pytest.raises(DependencyUnavailableError):
        await service.list_suppliers()
