"""Integration: specialists against real PostgreSQL, MongoDB, and Qdrant (phase 4)."""

import pytest
from app.agents.contracts import PolicyQuery, SupplierQuery
from app.agents.policy_specialist import PolicySpecialist
from app.agents.supplier_specialist import SupplierSpecialist
from app.core.config import get_settings
from app.database.mongodb.client import get_database
from app.database.postgres.session import get_session_factory
from app.rag.runtime import build_retriever
from app.repositories.supplier_profile_repository import SupplierProfileRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.policy_service import PolicyService
from app.services.supplier_candidate_service import SupplierCandidateService

pytestmark = pytest.mark.integration

AS_OF = "2026-01-15"


async def test_supplier_specialist_returns_real_candidates(
    live_client, seeded_postgres, seeded_mongodb
) -> None:
    settings = get_settings()
    async with get_session_factory()() as session:
        specialist = SupplierSpecialist(
            SupplierCandidateService(
                SupplierRepository(session),
                SupplierProfileRepository(get_database()),
            ),
            max_candidates=settings.workflow_max_supplier_candidates,
        )
        candidates = await specialist.search(
            SupplierQuery(
                product_id="PRD0001",
                category="electronics",
                quantity=100,
                constraints={},
                as_of=AS_OF,
            )
        )

    assert candidates
    assert all(candidate.quotation_id for candidate in candidates)
    assert all(candidate.supplier_id for candidate in candidates)
    # Batched Mongo profiles: at least one candidate carries a real profile document.
    assert any(candidate.profile for candidate in candidates)


async def test_policy_specialist_returns_cited_evidence(
    live_client, ingested_qdrant
) -> None:
    settings = get_settings()
    policy_service = PolicyService(
        build_retriever(settings),
        result_limit=settings.retrieval_result_limit,
        min_dense_score=settings.retrieval_min_dense_score,
        min_sparse_score=settings.retrieval_min_sparse_score,
        min_text_chars=settings.retrieval_min_text_chars,
    )
    specialist = PolicySpecialist(
        policy_service, max_evidence=settings.workflow_max_policy_evidence
    )

    result = await specialist.retrieve(
        PolicyQuery(
            text="procurement approval threshold electronics quantity",
            as_of=AS_OF,
            limit=settings.workflow_max_policy_evidence,
        )
    )

    assert result.inconclusive is False
    assert result.source_ids
    assert len(result.evidence) <= settings.workflow_max_policy_evidence
    assert all(item.chunk_id and item.text for item in result.evidence)
    assert all(item.document_id for item in result.evidence)
