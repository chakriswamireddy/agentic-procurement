from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.procurement import RecommendationSummary

WorkflowDecision = Literal["approved", "rejected"]


class WorkflowView(BaseModel):
    request_id: str
    thread_id: str
    status: str
    current_node: str | None = None
    awaiting_approval: bool = False
    failure_reason: str | None = None
    recommendation: RecommendationSummary | None = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    decision: WorkflowDecision
    approver_id: str = Field(
        description=(
            "Temporary client-supplied approver identifier for the development-only "
            "resume endpoint. Phase 5 derives the approver from the JWT subject and "
            "adds authorization and recommendation-version checks."
        )
    )
    reason: str | None = Field(default=None, max_length=2000)
