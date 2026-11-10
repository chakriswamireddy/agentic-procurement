from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from app.api.deps import (
    CurrentUserDep,
    WorkflowServiceDep,
    require_roles,
)
from app.core.authz import ensure_can_create_request, ensure_request_read
from app.core.logging import get_correlation_id
from app.schemas.auth import AuthenticatedUser
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
    current_user: Annotated[
        AuthenticatedUser, Depends(require_roles("requester", "admin"))
    ],
) -> ProcurementRequestResponse:
    """Create a request and run the workflow until approval or a terminal state.

    ``requester_id`` is always derived from the authenticated JWT subject.
    """
    ensure_can_create_request(current_user)
    response.headers["Cache-Control"] = "no-store"
    view = await service.create_and_start(
        requester_id=current_user.id,
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
    current_user: CurrentUserDep,
) -> ProcurementRequestResponse:
    response.headers["Cache-Control"] = "no-store"
    record = await service.get_request(request_id)
    ensure_request_read(
        current_user,
        type("R", (), {"requester_id": record["requester_id"]})(),
    )
    return ProcurementRequestResponse.model_validate(record)
