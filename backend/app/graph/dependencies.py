"""Per-run service dependencies for graph nodes.

The compiled graph is process-wide, but the services it calls are request-scoped (they
hold an ``AsyncSession``). A context variable keeps the graph reusable without binding
database sessions into the compiled object. Parallel LangGraph branches inherit the
context because asyncio copies context variables into child tasks.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol

from pymongo.asynchronous.database import AsyncDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.supplier_profile_repository import SupplierProfileRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.approval_service import ApprovalService
from app.services.comparison_service import ComparisonService
from app.services.execution_service import ExecutionService, FakeExecutionGateway
from app.services.policy_evidence_service import PolicyEvidenceService
from app.services.recommendation_service import RecommendationService
from app.services.recommendation_validation_service import RecommendationValidator
from app.services.request_validation_service import RequestValidator
from app.services.result_service import ResultService
from app.services.supplier_candidate_service import SupplierCandidateService


class SupplierCandidateProvider(Protocol):
    async def candidates(
        self, *, request: dict[str, Any], as_of: str
    ) -> list[dict[str, Any]]: ...


class PolicyEvidenceProvider(Protocol):
    async def evidence_for(
        self, *, request: dict[str, Any], as_of: str
    ) -> dict[str, Any]: ...


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
    suppliers: SupplierCandidateProvider
    policies: PolicyEvidenceProvider
    comparison: ComparisonService
    validator: RecommendationValidator
    recommendations: RecommendationProvider
    approvals: ApprovalRecorder
    execution: ExecutionRunner
    results: ResultRecorder
    supplier_timeout_seconds: float = 5.0
    policy_timeout_seconds: float = 8.0


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
    policy_service: Any,
) -> GraphDependencies:
    audit = AuditRepository(session)
    requests = RequestRepository(session)
    return GraphDependencies(
        request_validator=RequestValidator(),
        suppliers=SupplierCandidateService(
            SupplierRepository(session), SupplierProfileRepository(mongo_db)
        ),
        policies=PolicyEvidenceService(policy_service),
        comparison=ComparisonService(),
        validator=RecommendationValidator(),
        recommendations=RecommendationService(RecommendationRepository(session)),
        approvals=ApprovalService(ApprovalRepository(session), audit),
        execution=ExecutionService(
            FakeExecutionGateway(), ExecutionRepository(session), audit
        ),
        results=ResultService(requests, audit),
        supplier_timeout_seconds=settings.workflow_supplier_timeout_seconds,
        policy_timeout_seconds=settings.workflow_policy_timeout_seconds,
    )
