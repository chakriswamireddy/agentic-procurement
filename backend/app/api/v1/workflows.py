from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from app.api.deps import (
    CurrentUserDep,
    WorkflowServiceDep,
    require_roles,
)
from app.core.authz import ensure_can_approve, ensure_request_read
from app.schemas.auth import AuthenticatedUser
from app.schemas.workflow import ApprovalDecisionRequest, WorkflowView
from app.services.approval_policy_service import ApprovalPolicyService

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
    current_user: CurrentUserDep,
) -> WorkflowView:
    response.headers["Cache-Control"] = "no-store"
    req = await service.get_request(thread_id)
    ensure_request_read(
        current_user,
        type("R", (), {"requester_id": req["requester_id"]})(),
    )
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
    current_user: CurrentUserDep,
) -> WorkflowView:
    """Authenticated approval resume endpoint enforcing Policy POL-002 rules."""
    req = await service.get_request(thread_id)
    # Order matters: self-approval before generic role denial (POL-002 §1.3).
    ensure_can_approve(
        current_user,
        type("R", (), {"requester_id": req["requester_id"]})(),
    )
    ApprovalPolicyService.validate_approval(
        decision=payload.decision,
        approver_id=current_user.id,
        approver_role=current_user.role,
        requester_id=req["requester_id"],
        recommendation=req.get("recommendation"),
        expected_version=payload.recommendation_version,
        reason=payload.reason,
    )

    response.headers["Cache-Control"] = "no-store"
    decision_dict = {
        "decision": payload.decision,
        "approver_id": current_user.id,
        "reason": payload.reason,
    }
    return await service.resume(thread_id, decision_dict)


@router.post(
    "/{thread_id}/execution/retry",
    response_model=WorkflowView,
    operation_id="retry_workflow_execution",
)
async def retry_workflow_execution(
    service: WorkflowServiceDep,
    response: Response,
    thread_id: Annotated[str, Path(min_length=1, max_length=64)],
    current_user: Annotated[
        AuthenticatedUser, Depends(require_roles("admin", "approver"))
    ],
) -> WorkflowView:
    """Safely re-invoke execution with the same idempotency key (Phase 5.13)."""
    from app.core.authz import ensure_can_retry_execution

    ensure_can_retry_execution(current_user)
    response.headers["Cache-Control"] = "no-store"
    return await service.retry_execution(thread_id, actor_id=current_user.id)
