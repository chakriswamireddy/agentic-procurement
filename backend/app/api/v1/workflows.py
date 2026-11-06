from typing import Annotated

from fastapi import APIRouter, Path, Request, Response

from app.api.deps import WorkflowServiceDep
from app.core.errors import ForbiddenError
from app.schemas.workflow import ApprovalDecisionRequest, WorkflowView

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get(
    "/{thread_id}",
    response_model=WorkflowView,
    operation_id="get_workflow_status",
)
async def get_workflow_status(
    service: WorkflowServiceDep,
    response: Response,
    thread_id: Annotated[str, Path(min_length=1, max_length=64)],
) -> WorkflowView:
    response.headers["Cache-Control"] = "no-store"
    return await service.get_status(thread_id)


@router.post(
    "/{thread_id}/approval",
    response_model=WorkflowView,
    operation_id="resume_workflow_approval",
)
async def resume_workflow_approval(
    request: Request,
    service: WorkflowServiceDep,
    response: Response,
    thread_id: Annotated[str, Path(min_length=1, max_length=64)],
    payload: ApprovalDecisionRequest,
) -> WorkflowView:
    """Development-only resume endpoint.

    Phase 5 replaces this with an authenticated approval API that checks the approver's
    role, the recommendation version, and idempotency before resuming.
    """
    settings = request.app.state.settings
    if settings.app_env != "development":
        raise ForbiddenError("approval resume is disabled outside development")

    response.headers["Cache-Control"] = "no-store"
    return await service.resume(
        thread_id,
        payload.model_dump(exclude_none=True),
    )
