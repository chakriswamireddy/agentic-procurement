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
    reason: str | None = Field(default=None, max_length=2000)
    recommendation_version: int | None = Field(
        default=None,
        description="Version of the recommendation being approved or rejected.",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description="Optional client key; derived from request/version/decision when omitted.",
    )
