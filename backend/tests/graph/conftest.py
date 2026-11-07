"""Shared fakes for graph tests.

The graph's nodes resolve specialists from ``GraphDependencies`` through a context
variable. These fakes replace every specialist that would touch PostgreSQL, MongoDB,
or Qdrant while keeping the real deterministic logic (comparison, scoring, validation)
under test through the real specialist wrappers.

Test budgets use ``max_attempts=1`` and tiny delays: retry behaviour belongs to the
runner tests, not to every graph test.
"""

from typing import Any

import pytest
from app.agents.analysis_specialist import AnalysisSpecialist
from app.agents.contracts import (
    PolicyEvidence,
    PolicyEvidenceResult,
    PolicyQuery,
    SupplierCandidate,
    SupplierQuery,
    TransientError,
)
from app.agents.explanation_service import ExplanationService
from app.agents.runner import SpecialistMetrics
from app.agents.validation_specialist import ValidationSpecialist
from app.graph.dependencies import GraphDependencies
from app.graph.orchestrator import NodeBudget, WorkflowBudgets
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


def make_budgets() -> WorkflowBudgets:
    """Graph-test budgets: one attempt, negligible delays, same topology as settings."""
    return WorkflowBudgets(
        supplier_lookup=NodeBudget("supplier_lookup", 5.0, 1, 12.0),
        policy_retrieval=NodeBudget("policy_retrieval", 5.0, 1, 12.0),
        compare_options=NodeBudget("compare_options", 1.0, 1, 2.0),
        validate_recommendation=NodeBudget("validate_recommendation", 1.0, 1, 2.0),
        execute_tool=NodeBudget("execute_tool", 10.0, 1, 15.0),
        base_delay_s=0.001,
        max_delay_s=0.002,
        max_candidates=200,
        max_evidence=5,
    )


class FakeSuppliers:
    """Stands in for SupplierSpecialist: same contract, same error mapping."""

    def __init__(self, results: list[dict] | None = None, error: Exception | None = None):
        self.results = results if results is not None else [make_candidate()]
        self.error = error
        self.calls: list[dict] = []

    async def search(self, query: SupplierQuery) -> list[SupplierCandidate]:
        self.calls.append(
            {"as_of": query.as_of, "request": query.to_request_payload()}
        )
        if self.error is not None:
            if isinstance(self.error, TransientError):
                raise self.error
            raise TransientError(
                self.error.__class__.__name__ or "supplier unavailable",
                code="supplier_db_unavailable",
            )
        return [SupplierCandidate.from_dict(item) for item in self.results]


class FakePolicies:
    """Stands in for PolicySpecialist: same contract, same error mapping."""

    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result = result if result is not None else make_policy_result()
        self.error = error
        self.calls: list[dict] = []

    async def retrieve(self, query: PolicyQuery) -> PolicyEvidenceResult:
        self.calls.append({"as_of": query.as_of, "text": query.text})
        if self.error is not None:
            if isinstance(self.error, TransientError):
                raise self.error
            raise TransientError(
                self.error.__class__.__name__ or "policy unavailable",
                code="policy_index_unavailable",
            )
        payload = dict(self.result)
        evidence = tuple(
            PolicyEvidence.from_dict(item)
            for item in payload.get("evidence") or []
        )
        return PolicyEvidenceResult(
            query=str(payload.get("query", query.text)),
            inconclusive=bool(payload.get("inconclusive")),
            reason=payload.get("reason"),
            evidence=evidence,
        )


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
        comparison=AnalysisSpecialist(),
        validator=ValidationSpecialist(),
        recommendations=FakeRecommendations(),
        approvals=FakeApprovals(),
        execution=FakeExecution(result=execution_result, error=execution_error),
        results=FakeResults(),
        budgets=make_budgets(),
        metrics=SpecialistMetrics(),
        explanation=ExplanationService(),
    )


@pytest.fixture
def dependencies() -> GraphDependencies:
    return make_dependencies()
