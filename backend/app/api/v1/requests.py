from typing import Annotated

from fastapi import APIRouter, Path, Response

from app.api.deps import WorkflowServiceDep
from app.core.logging import get_correlation_id
from app.schemas.procurement import (
    CreateProcurementRequest,
    ProcurementRequestResponse,
)

router = APIRouter(prefix="/procurement/requests", tags=["procurement"])


@router.post(
    "",
    response_model=ProcurementRequestResponse,
    status_code=201,
    operation_id="create_procurement_request",
)
async def create_procurement_request(
    payload: CreateProcurementRequest,
    service: WorkflowServiceDep,
    response: Response,
) -> ProcurementRequestResponse:
    """Create a request and run the workflow until approval or a terminal state.

    ``requester_id`` is temporary until Phase 5 derives it from a JWT. Request creation
    and graph start are intentionally combined, so a new request returns 201 with the
    paused workflow state rather than a bare 202.
    """
    response.headers["Cache-Control"] = "no-store"
    view = await service.create_and_start(
        requester_id=payload.requester_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        constraints=payload.constraints.model_dump(mode="json"),
        correlation_id=get_correlation_id() or "",
    )
    record = await service.get_request(view.request_id)
    response.headers["X-Workflow-Status"] = view.status
    return ProcurementRequestResponse.model_validate(record)


@router.get(
    "/{request_id}",
    response_model=ProcurementRequestResponse,
    operation_id="get_procurement_request",
)
async def get_procurement_request(
    service: WorkflowServiceDep,
    response: Response,
    request_id: Annotated[str, Path(min_length=1, max_length=64)],
) -> ProcurementRequestResponse:
    response.headers["Cache-Control"] = "no-store"
    record = await service.get_request(request_id)
    return ProcurementRequestResponse.model_validate(record)
