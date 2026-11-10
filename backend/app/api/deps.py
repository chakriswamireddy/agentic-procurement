from typing import Annotated

from fastapi import Depends, Request
from pymongo.asynchronous.database import AsyncDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mongodb.client import get_database
from app.database.postgres.session import get_db_session
from app.database.redis.cache import SupplierCache
from app.database.redis.client import get_redis
from app.graph.builder import build_graph
from app.rag.runtime import build_retriever
from app.repositories.document_repository import DocumentRepository
from app.repositories.supplier_profile_repository import SupplierProfileRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.document_service import DocumentService
from app.services.policy_service import PolicyService
from app.services.supplier_service import SupplierService
from app.services.workflow_service import WorkflowService


def get_mongo_db() -> AsyncDatabase:
    return get_database()


def get_supplier_cache(request: Request) -> SupplierCache | None:
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not getattr(settings, "redis_cache_enabled", True):
        return None
    try:
        redis_client = get_redis()
        return SupplierCache(
            redis_client,
            base_ttl=getattr(settings, "redis_cache_ttl_seconds", 60),
            enabled=getattr(settings, "redis_cache_enabled", True),
        )
    except Exception:
        return None


def get_supplier_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    mongo_db: Annotated[AsyncDatabase, Depends(get_mongo_db)],
    cache: Annotated[SupplierCache | None, Depends(get_supplier_cache)] = None,
) -> SupplierService:
    return SupplierService(
        suppliers=SupplierRepository(session),
        profiles=SupplierProfileRepository(mongo_db),
        cache=cache,
    )


def get_policy_service(request: Request) -> PolicyService:
    settings = request.app.state.settings
    return PolicyService(
        build_retriever(settings),
        result_limit=settings.retrieval_result_limit,
        min_dense_score=settings.retrieval_min_dense_score,
        min_sparse_score=settings.retrieval_min_sparse_score,
        min_text_chars=settings.retrieval_min_text_chars,
    )


def get_document_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentService:
    return DocumentService(
        DocumentRepository(session),
        request.app.state.settings,
    )


def get_workflow_graph(request: Request):
    graph = getattr(request.app.state, "workflow_graph", None)
    if graph is None:
        graph = build_graph()
        request.app.state.workflow_graph = graph
    return graph


def get_workflow_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    mongo_db: Annotated[AsyncDatabase, Depends(get_mongo_db)],
) -> WorkflowService:
    return WorkflowService(
        request.app.state.settings,
        get_workflow_graph(request),
        session=session,
        mongo_db=mongo_db,
        policy_service=get_policy_service(request),
    )


SupplierServiceDep = Annotated[SupplierService, Depends(get_supplier_service)]
PolicyServiceDep = Annotated[PolicyService, Depends(get_policy_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]
