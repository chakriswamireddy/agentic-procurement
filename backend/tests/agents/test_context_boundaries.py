"""Context boundaries: specialists see only their DTO, never the whole state (4.10)."""

import dataclasses

from app.agents.contracts import (
    FORBIDDEN_CONTEXT_FIELDS,
    ComparisonRequest,
    ComparisonResult,
    PolicyEvidence,
    PolicyEvidenceResult,
    PolicyQuery,
    RequestFacts,
    SupplierCandidate,
    SupplierQuery,
    ValidationRequest,
    ValidationResult,
    dto_field_names,
)
from app.agents.supplier_specialist import SupplierSpecialist
from app.graph.builder import build_graph
from app.graph.dependencies import use_dependencies
from tests.graph.conftest import make_dependencies, make_state

ALL_DTOS = (
    SupplierQuery,
    SupplierCandidate,
    PolicyQuery,
    PolicyEvidence,
    PolicyEvidenceResult,
    ComparisonRequest,
    ComparisonResult,
    ValidationRequest,
    ValidationResult,
    RequestFacts,
)

SUPPLIER_FIELDS = {"product_id", "category", "quantity", "constraints", "as_of"}
POLICY_FIELDS = {"text", "as_of", "limit", "classifications", "document_ids"}


def test_supplier_dto_is_exactly_the_allowlist() -> None:
    assert dto_field_names(SupplierQuery) == SUPPLIER_FIELDS


def test_policy_dto_is_exactly_the_allowlist() -> None:
    assert dto_field_names(PolicyQuery) == POLICY_FIELDS


def test_no_dto_carries_forbidden_context_fields() -> None:
    for dto in ALL_DTOS:
        leaked = dto_field_names(dto) & FORBIDDEN_CONTEXT_FIELDS
        assert not leaked, f"{dto.__name__} exposes forbidden fields: {leaked}"


def test_supplier_dto_has_no_nested_approval_or_policy_data() -> None:
    names = dto_field_names(SupplierQuery)
    assert "policy_evidence" not in names
    assert "recommendation" not in names
    assert "approval" not in names
    assert "execution" not in names


async def test_specialist_receives_a_dto_not_the_graph_state() -> None:
    """The node must hand the specialist a SupplierQuery, never ProcurementState."""
    received: list[object] = []

    class RecordingSpecialist:
        async def search(self, query):
            received.append(query)
            return []

    dependencies = make_dependencies()
    dependencies.suppliers = RecordingSpecialist()
    graph = build_graph()
    state = make_state()

    with use_dependencies(dependencies):
        await graph.ainvoke(state, {"configurable": {"thread_id": state["thread_id"]}})

    assert len(received) == 1
    query = received[0]
    assert isinstance(query, SupplierQuery)
    # The DTO is frozen and carries no state keys such as errors, approval, or user_id.
    assert dataclasses.is_dataclass(query)
    assert "user_id" not in dto_field_names(type(query))
    assert "errors" not in dto_field_names(type(query))


async def test_supplier_port_only_receives_request_fields() -> None:
    """The port payload is a strict subset of what the specialist is allowed to see."""
    payloads: list[dict] = []

    class RecordingPort:
        async def candidates(self, *, request: dict, as_of: str):
            payloads.append(dict(request))
            return []

    specialist = SupplierSpecialist(RecordingPort())
    query = SupplierQuery.from_request(
        {
            "product_id": "PRD0001",
            "category": "electronics",
            "quantity": 10,
            "constraints": {"max_delivery_days": 14},
            "approval": {"decision": "approved"},
            "user_id": "USR0001",
            "token": "secret-jwt",
        },
        as_of="2026-01-15",
    )

    await specialist.search(query)

    assert len(payloads) == 1
    assert set(payloads[0]) == {"product_id", "category", "quantity", "constraints"}
    assert "token" not in payloads[0]
    assert "approval" not in payloads[0]
    assert "user_id" not in payloads[0]
