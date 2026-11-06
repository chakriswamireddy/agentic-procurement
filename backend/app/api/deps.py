from typing import Annotated

from fastapi import Depends, Request
from pymongo.asynchronous.database import AsyncDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mongodb.client import get_database
from app.database.postgres.session import get_db_session
from app.rag.runtime import build_retriever
from app.repositories.document_repository import DocumentRepository
from app.repositories.supplier_profile_repository import SupplierProfileRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.document_service import DocumentService
from app.services.policy_service import PolicyService
from app.services.supplier_service import SupplierService


def get_mongo_db() -> AsyncDatabase:
    return get_database()


def get_supplier_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    mongo_db: Annotated[AsyncDatabase, Depends(get_mongo_db)],
) -> SupplierService:
    return SupplierService(
        suppliers=SupplierRepository(session),
        profiles=SupplierProfileRepository(mongo_db),
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


SupplierServiceDep = Annotated[SupplierService, Depends(get_supplier_service)]
PolicyServiceDep = Annotated[PolicyService, Depends(get_policy_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
