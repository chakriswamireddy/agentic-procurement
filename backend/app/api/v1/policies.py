from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import PolicyServiceDep
from app.schemas.policy import PolicySearchResponse

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get(
    "/search",
    response_model=PolicySearchResponse,
    operation_id="search_policies",
)
async def search_policies(
    service: PolicyServiceDep,
    response: Response,
    q: Annotated[str, Query(min_length=3, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    as_of: Annotated[date | None, Query()] = None,
    classification: Annotated[list[str] | None, Query()] = None,
    document_ids: Annotated[list[str] | None, Query()] = None,
) -> PolicySearchResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.search(
        q,
        limit=limit,
        as_of=as_of,
        classifications=tuple(classification) if classification else None,
        document_ids=tuple(document_ids) if document_ids else None,
    )
