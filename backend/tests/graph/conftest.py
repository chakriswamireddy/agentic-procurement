"""Shared fakes for graph tests.

The graph's nodes resolve services from ``GraphDependencies`` through a context
variable. These fakes replace every service that would touch PostgreSQL, MongoDB,
or Qdrant while keeping the real deterministic logic (validators, comparison,
scoring) under test.
"""

from typing import Any

import pytest
from app.graph.dependencies import GraphDependencies
from app.services.comparison_service import ComparisonService
from app.services.recommendation_validation_service import RecommendationValidator
from app.services.request_validation_service import RequestValidator

AS_OF = "2026-01-15"


def make_request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "product_id": "PRD0001",
        "product_name": "Essential Monitor",
        "category": "electronics",
        "quantity": 100,
        "currency": "INR",
        "constraints": {},
    }
    request.update(overrides)
    return request


def make_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "request_id": "PRQ-TEST00000001",
        "thread_id": "PRQ-TEST00000001",
        "user_id": "USR0001",
        "correlation_id": "corr-test-1",
        "as_of": AS_OF,
        "request": make_request(),
        "errors": [],
        "status": "received",
    }
    state.update(overrides)
    return state


def make_candidate(**overrides: Any) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "supplier_id": "SUP0001",
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
    candidate.update(overrides)
    return candidate


def make_evidence(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "chunk_id": "chunk-0001",
        "document_id": "POL-001",
        "version": "3.2",
        "title": "Procurement Policy",
        "section_path": "4.1 Thresholds",
        "text": "Purchases above threshold require approval.",
        "score": 0.05,
        "dense_rank": 1,
        "sparse_rank": 1,
        "source_path": "data/documents/policy-001.md",
        "effective_from": "2026-01-01",
        "status": "active",
        "classification": "internal",
        "injection_suspected": False,
    }
    item.update(overrides)
    return item


def make_policy_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "query": (
            "Essential Monitor electronics procurement approval threshold quantity 100 "
            "delivery standard certifications none"
        ),
        "inconclusive": False,
        "reason": None,
        "evidence": [make_evidence()],
    }
    result.update(overrides)
    return result


class FakeSuppliers:
    def __init__(self, results: list[dict] | None = None, error: Exception | None = None):
        self.results = results if results is not None else [make_candidate()]
        self.error = error
        self.calls: list[dict] = []

    async def candidates(self, *, request: dict, as_of: str) -> list[dict]:
        self.calls.append({"request": request, "as_of": as_of})
        if self.error is not None:
            raise self.error
        return list(self.results)


class FakePolicies:
    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result = result if result is not None else make_policy_result()
        self.error = error
        self.calls: list[dict] = []

    async def evidence_for(self, *, request: dict, as_of: str) -> dict:
        self.calls.append({"request": request, "as_of": as_of})
        if self.error is not None:
            raise self.error
        return dict(self.result)


class FakeRecommendations:
    """Mirrors RecommendationService output shape without touching PostgreSQL."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def prepare_and_persist(
        self, *, request, comparison, policy_evidence, policy_query, issues
    ) -> dict | None:
        self.calls.append(
            {
                "request_id": request.get("request_id"),
                "policy_query": policy_query,
                "issues": issues,
            }
        )
        recommended = comparison.get("recommended")
        if not recommended:
            return None
        rationale = comparison.get("rationale") or {}
        return {
            "id": "REC-TEST",
            "supplier_id": recommended["supplier_id"],
            "supplier_name": recommended["supplier_name"],
            "score": recommended["total_score"],
            "scoring_version": rationale.get("scoring_version", "1.0"),
            "total_cost": recommended["total_cost"],
            "unit_price": recommended["unit_price"],
            "currency": recommended["currency"],
            "delivery_days": recommended["delivery_days"],
            "valid_until": recommended["valid_until"],
            "risk_level": recommended["risk_level"],
            "rationale": {"scoring_version": rationale.get("scoring_version", "1.0")},
            "evidence": list(policy_evidence),
            "evidence_query": policy_query,
            "caveats": [f"risk level: {recommended['risk_level']}"],
            "version": 1,
            "persisted": True,
        }


class FakeApprovals:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def record(self, *, state: dict, approval: dict) -> dict:
        self.calls.append(dict(approval))
        return {**approval, "id": "APR-TEST", "persisted": True}


class FakeExecution:
    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def execute(self, *, state: dict) -> dict:
        self.calls.append(state["request_id"])
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return dict(self.result)
        version = int(state["recommendation"]["version"])
        return {
            "success": True,
            "idempotency_key": f"{state['request_id']}:{version}",
            "external_reference": f"SIM-{state['request_id']}-{version}",
            "recoverable": False,
            "error_code": None,
        }


class FakeResults:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def record_result(self, *, state: dict, status: str) -> None:
        self.calls.append({"request_id": state.get("request_id"), "status": status})


def make_dependencies(
    *,
    candidates: list[dict] | None = None,
    supplier_error: Exception | None = None,
    policy_result: dict | None = None,
    policy_error: Exception | None = None,
    execution_result: dict | None = None,
    execution_error: Exception | None = None,
) -> GraphDependencies:
    return GraphDependencies(
        request_validator=RequestValidator(),
        suppliers=FakeSuppliers(results=candidates, error=supplier_error),
        policies=FakePolicies(result=policy_result, error=policy_error),
        comparison=ComparisonService(),
        validator=RecommendationValidator(),
        recommendations=FakeRecommendations(),
        approvals=FakeApprovals(),
        execution=FakeExecution(result=execution_result, error=execution_error),
        results=FakeResults(),
        supplier_timeout_seconds=5.0,
        policy_timeout_seconds=8.0,
    )


@pytest.fixture
def dependencies() -> GraphDependencies:
    return make_dependencies()
