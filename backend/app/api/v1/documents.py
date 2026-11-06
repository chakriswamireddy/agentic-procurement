from typing import Annotated

from fastapi import APIRouter, File, Path, Query, Response, UploadFile, status

from app.api.deps import DocumentServiceDep
from app.schemas.document import (
    DocumentStatus,
    PolicyDocumentList,
    PolicyDocumentRecord,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=PolicyDocumentRecord,
    status_code=status.HTTP_201_CREATED,
    operation_id="upload_document",
)
async def upload_document(
    service: DocumentServiceDep,
    response: Response,
    file: Annotated[UploadFile, File()],
) -> PolicyDocumentRecord:
    content = await file.read()
    record = await service.upload(file.filename or "upload.md", content)
    response.headers["Location"] = f"/api/v1/documents/{record.id}"
    return record


@router.get(
    "",
    response_model=PolicyDocumentList,
    operation_id="list_documents",
)
async def list_documents(
    service: DocumentServiceDep,
    response: Response,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
) -> PolicyDocumentList:
    response.headers["Cache-Control"] = "no-store"
    items = await service.list_documents(status_filter)
    return PolicyDocumentList(items=items, total=len(items))


@router.get(
    "/{document_id}",
    response_model=PolicyDocumentRecord,
    operation_id="get_document",
)
async def get_document(
    service: DocumentServiceDep,
    response: Response,
    document_id: Annotated[str, Path(min_length=1, max_length=64)],
    version: Annotated[str | None, Query(max_length=32)] = None,
) -> PolicyDocumentRecord:
    response.headers["Cache-Control"] = "no-store"
    return await service.get_document(document_id, version)


@router.post(
    "/{document_id}/ingest",
    response_model=PolicyDocumentRecord,
    operation_id="ingest_document",
)
async def ingest_document(
    service: DocumentServiceDep,
    response: Response,
    document_id: str,
    version: Annotated[str | None, Query(max_length=32)] = None,
) -> PolicyDocumentRecord:
    response.headers["Cache-Control"] = "no-store"
    return await service.ingest(document_id, version)
