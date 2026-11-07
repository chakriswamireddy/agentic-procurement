"""Per-run service dependencies for graph nodes.

The compiled graph is process-wide, but the services it calls are request-scoped (they
hold an ``AsyncSession``). A context variable keeps the graph reusable without binding
database sessions into the compiled object. Parallel LangGraph branches inherit the
context because asyncio copies context variables into child tasks.

Context boundary rule (phase 4): nodes receive specialists through narrow protocols, and
specialists receive DTOs — never the whole graph state, never a connection string, never
approval or execution records.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol

from pymongo.asynchronous.database import AsyncDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysis_specialist import AnalysisSpecialist
from app.agents.contracts import (
    ComparisonRequest,
    ComparisonResult,
    PolicyEvidenceResult,
    PolicyQuery,
    SupplierCandidate,
    SupplierQuery,
    ValidationRequest,
    ValidationResult,
)
from app.agents.explanation_service import ExplanationService
from app.agents.policy_specialist import PolicySpecialist
from app.agents.runner import SpecialistMetrics
from app.agents.supplier_specialist import SupplierSpecialist
from app.agents.validation_specialist import ValidationSpecialist
from app.core.config import Settings
from app.graph.orchestrator import WorkflowBudgets, budgets_from_settings
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.supplier_profile_repository import SupplierProfileRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.approval_service import ApprovalService
from app.services.execution_service import ExecutionService, FakeExecutionGateway
from app.services.policy_service import PolicyService
from app.services.recommendation_service import RecommendationService
from app.services.request_validation_service import RequestValidator
from app.services.result_service import ResultService
from app.services.supplier_candidate_service import SupplierCandidateService


class SupplierSearchPort(Protocol):
    async def search(self, query: SupplierQuery) -> list[SupplierCandidate]: ...


class PolicySearchPort(Protocol):
    async def retrieve(self, query: PolicyQuery) -> PolicyEvidenceResult: ...


class AnalysisPort(Protocol):
    async def compare(self, request: ComparisonRequest) -> ComparisonResult: ...


class ValidationPort(Protocol):
    async def validate(self, request: ValidationRequest) -> ValidationResult: ...


class RecommendationProvider(Protocol):
    async def prepare_and_persist(
        self,
        *,
        request: dict[str, Any],
        comparison: dict[str, Any],
        policy_evidence: list[dict[str, Any]],
        policy_query: str,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any] | None: ...


class ApprovalRecorder(Protocol):
    async def record(
        self, *, state: dict[str, Any], approval: dict[str, Any]
    ) -> dict[str, Any]: ...


class ExecutionRunner(Protocol):
    async def execute(self, *, state: dict[str, Any]) -> dict[str, Any]: ...


class ResultRecorder(Protocol):
    async def record_result(self, *, state: dict[str, Any], status: str) -> None: ...


@dataclass
class GraphDependencies:
    request_validator: RequestValidator
    suppliers: SupplierSearchPort
    policies: PolicySearchPort
    comparison: AnalysisPort
    validator: ValidationPort
    recommendations: RecommendationProvider
    approvals: ApprovalRecorder
    execution: ExecutionRunner
    results: ResultRecorder
    budgets: WorkflowBudgets
    metrics: SpecialistMetrics = field(default_factory=SpecialistMetrics)
    explanation: ExplanationService = field(default_factory=ExplanationService)


_dependencies: ContextVar[GraphDependencies | None] = ContextVar(
    "graph_dependencies", default=None
)


@contextmanager
def use_dependencies(dependencies: GraphDependencies):
    token = _dependencies.set(dependencies)
    try:
        yield dependencies
    finally:
        _dependencies.reset(token)


def get_dependencies() -> GraphDependencies:
    dependencies = _dependencies.get()
    if dependencies is None:
        raise RuntimeError("graph dependencies have not been configured for this run")
    return dependencies


def build_dependencies(
    settings: Settings,
    *,
    session: AsyncSession,
    mongo_db: AsyncDatabase,
    policy_service: PolicyService,
) -> GraphDependencies:
    audit = AuditRepository(session)
    requests = RequestRepository(session)
    return GraphDependencies(
        request_validator=RequestValidator(),
        suppliers=SupplierSpecialist(
            SupplierCandidateService(
                SupplierRepository(session), SupplierProfileRepository(mongo_db)
            ),
            max_candidates=settings.workflow_max_supplier_candidates,
        ),
        policies=PolicySpecialist(
            policy_service, max_evidence=settings.workflow_max_policy_evidence
        ),
        comparison=AnalysisSpecialist(),
        validator=ValidationSpecialist(),
        recommendations=RecommendationService(RecommendationRepository(session)),
        approvals=ApprovalService(ApprovalRepository(session), audit),
        execution=ExecutionService(
            FakeExecutionGateway(), ExecutionRepository(session), audit
        ),
        results=ResultService(requests, audit),
        budgets=budgets_from_settings(settings),
        metrics=SpecialistMetrics(),
        explanation=ExplanationService(),
    )
