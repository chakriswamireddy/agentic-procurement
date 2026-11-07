"""Supplier specialist: candidates, error mapping, caps, and batched profiles (4.3)."""

from datetime import date
from types import SimpleNamespace

from app.agents.contracts import PermanentError, SupplierQuery, TransientError
from app.agents.runner import run_specialist
from app.agents.supplier_specialist import SupplierSpecialist
from app.services.supplier_candidate_service import SupplierCandidateService
from pymongo.errors import ServerSelectionTimeoutError

AS_OF = "2026-01-15"


def make_query(**overrides) -> SupplierQuery:
    values = {
        "product_id": "PRD0001",
        "category": "electronics",
        "quantity": 100,
        "constraints": {},
        "as_of": AS_OF,
    }
    values.update(overrides)
    return SupplierQuery(**values)


def make_row(supplier_id: str = "SUP0001", **overrides) -> dict:
    row = {
        "supplier_id": supplier_id,
        "supplier_name": "Apex Components Pvt Ltd",
        "supplier_category": "electronics",
        "supplier_status": "active",
        "quotation_id": "QTN00001",
        "product_id": "PRD0001",
        "unit_price": "100.00",
        "currency": "INR",
        "available_quantity": 1000,
        "delivery_days": 10,
        "valid_until": "2026-06-01",
        "profile": {
            "certifications": ["ISO9001"],
            "compliance": {"risk_level": "low", "verification_status": "verified"},
        },
    }
    row.update(overrides)
    return row


class FakeSupplierPort:
    def __init__(self, rows=None, error=None):
        self.rows = rows if rows is not None else [make_row()]
        self.error = error
        self.calls: list[dict] = []

    async def candidates(self, *, request: dict, as_of: str) -> list[dict]:
        self.calls.append({"request": request, "as_of": as_of})
        if self.error is not None:
            raise self.error
        return list(self.rows)


async def test_returns_candidates_with_quotes_and_profiles() -> None:
    port = FakeSupplierPort()
    specialist = SupplierSpecialist(port)

    candidates = await specialist.search(make_query())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.supplier_id == "SUP0001"
    assert candidate.quotation_id == "QTN00001"
    assert candidate.unit_price == "100.00"
    assert candidate.profile is not None
    assert candidate.profile["certifications"] == ["ISO9001"]
    assert port.calls[0]["request"]["product_id"] == "PRD0001"
    assert port.calls[0]["as_of"] == AS_OF


async def test_missing_profile_degrades_to_empty_profile() -> None:
    port = FakeSupplierPort(rows=[make_row(profile=None)])
    specialist = SupplierSpecialist(port)

    candidates = await specialist.search(make_query())

    assert len(candidates) == 1
    assert candidates[0].profile is None
    assert candidates[0].to_dict()["profile"] is None


async def test_empty_result_is_not_an_error() -> None:
    specialist = SupplierSpecialist(FakeSupplierPort(rows=[]))

    assert await specialist.search(make_query()) == []


async def test_db_failure_maps_to_transient_error() -> None:
    specialist = SupplierSpecialist(FakeSupplierPort(error=ConnectionError("refused")))

    try:
        await specialist.search(make_query())
    except TransientError as exc:
        assert exc.code == "supplier_db_unavailable"
        assert exc.transient is True
    else:
        raise AssertionError("expected a TransientError")


async def test_invalid_query_is_permanent_and_skips_the_port() -> None:
    port = FakeSupplierPort()
    specialist = SupplierSpecialist(port)

    try:
        await specialist.search(make_query(quantity=0))
    except PermanentError as exc:
        assert exc.code == "invalid_supplier_query"
        assert exc.transient is False
    else:
        raise AssertionError("expected a PermanentError")
    assert port.calls == []


async def test_runner_retries_transient_supplier_failures() -> None:
    """The specialist maps dependency failures so the runner can retry them."""
    specialist = SupplierSpecialist(FakeSupplierPort(error=ConnectionError("refused")))
    calls = {"n": 0}
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async def operation() -> list:
        nonlocal calls
        calls["n"] += 1
        return await specialist.search(make_query())

    result = await run_specialist(
        name="supplier_lookup",
        operation=operation,
        timeout_s=1.0,
        correlation_id="corr-sup",
        max_attempts=3,
        base_delay_s=0.01,
        sleep=sleep,
    )

    assert result.ok is False
    assert result.attempts == 3
    assert calls["n"] == 3
    assert len(sleeps) == 2
    assert result.error is not None
    assert result.error.code == "supplier_db_unavailable"
    assert result.error.transient is True


async def test_candidate_set_is_capped() -> None:
    rows = [make_row(supplier_id=f"SUP{i:04d}", quotation_id=f"QTN{i:05d}") for i in range(250)]
    specialist = SupplierSpecialist(FakeSupplierPort(rows=rows), max_candidates=200)

    candidates = await specialist.search(make_query())

    assert len(candidates) == 200


async def test_profile_lookup_is_batched_not_n_plus_one() -> None:
    """One Mongo batch call for all candidates, not one call per supplier."""

    class CountingProfiles:
        def __init__(self) -> None:
            self.batch_calls = 0
            self.single_calls = 0

        async def get_profiles(self, supplier_ids: list):
            self.batch_calls += 1
            return {
                supplier_id: SimpleNamespace(
                    model_dump=lambda mode="json": {"certifications": []}
                )
                for supplier_id in supplier_ids
            }

        async def get_profile(self, supplier_id: str):
            self.single_calls += 1
            return None

    class FakeRepository:
        async def list_quotation_candidates(self, product_id: str):
            return [
                (SimpleNamespace(id=f"SUP{i:04d}", name="S", category="electronics",
                                 status="active"),
                 SimpleNamespace(id=f"QTN{i:05d}", product_id=product_id,
                                 unit_price="10.00", currency="INR",
                                 available_quantity=10, delivery_days=5,
                                 valid_until=date(2026, 6, 1)))
                for i in range(5)
            ]

    profiles = CountingProfiles()
    service = SupplierCandidateService(FakeRepository(), profiles)

    candidates = await service.candidates(
        request={"product_id": "PRD0001"}, as_of=AS_OF
    )

    assert len(candidates) == 5
    assert profiles.batch_calls == 1
    assert profiles.single_calls == 0


async def test_mongo_outage_is_retryable_not_unexpected() -> None:
    """A PyMongo failure during profile lookup must translate to a retryable error.

    ServerSelectionTimeoutError is a PyMongoError (not OSError/TimeoutError), so the
    service layer translates it to DependencyUnavailableError; without that the runner
    would wrap it as a non-retryable unexpected error and never retry an outage.
    """

    class FailingProfiles:
        async def get_profiles(self, supplier_ids: list) -> dict:
            raise ServerSelectionTimeoutError("10.255.255.1:27017: timed out")

        async def get_profile(self, supplier_id: str) -> None:
            raise ServerSelectionTimeoutError("10.255.255.1:27017: timed out")

    class FakeRepository:
        async def list_quotation_candidates(self, product_id: str):
            return [
                (
                    SimpleNamespace(
                        id="SUP0001",
                        name="Apex Components Pvt Ltd",
                        category="electronics",
                        status="active",
                    ),
                    SimpleNamespace(
                        id="QTN00001",
                        product_id=product_id,
                        unit_price="100.00",
                        currency="INR",
                        available_quantity=1000,
                        delivery_days=10,
                        valid_until=date(2026, 6, 1),
                    ),
                )
            ]

    specialist = SupplierSpecialist(
        SupplierCandidateService(FakeRepository(), FailingProfiles())
    )
    calls = {"n": 0}

    async def operation() -> list:
        nonlocal calls
        calls["n"] += 1
        return await specialist.search(make_query())

    async def no_sleep(_delay: float) -> None:
        return None

    result = await run_specialist(
        name="supplier_lookup",
        operation=operation,
        timeout_s=1.0,
        correlation_id="corr-mongo",
        max_attempts=3,
        base_delay_s=0.01,
        sleep=no_sleep,
    )

    assert result.ok is False
    assert result.attempts == 3
    assert calls["n"] == 3
    assert result.error is not None
    assert result.error.code == "supplier_db_unavailable"
    assert result.error.transient is True
