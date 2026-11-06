"""Typed state for the procurement workflow graph.

The graph state is execution state, not a business record. Business facts live in
PostgreSQL (requests, recommendations, approvals, execution records, audit events).
Every value stored here must be JSON-serializable because the checkpointer persists it.

Deviation from the phase guide: ``policy_status`` was added so the policy node can
return an explicit inconclusive result without inventing fake evidence. ``failure_reason``
carries a machine-readable terminal reason for the audit trail.
"""

import operator
from typing import Annotated, Literal, NotRequired, TypedDict

WorkflowStatus = Literal[
    "received",
    "researching",
    "awaiting_approval",
    "approved",
    "rejected",
    "executed",
    "failed",
    "needs_info",
    "inconclusive",
]


class ProcurementState(TypedDict):
    request_id: str
    thread_id: str
    user_id: str
    correlation_id: str
    as_of: str
    request: dict
    supplier_results: NotRequired[list[dict]]
    policy_evidence: NotRequired[list[dict]]
    policy_status: NotRequired[dict]
    comparison: NotRequired[dict]
    validation: NotRequired[dict]
    recommendation: NotRequired[dict]
    approval: NotRequired[dict]
    execution: NotRequired[dict]
    failure_reason: NotRequired[str]
    errors: Annotated[list[dict], operator.add]
    status: WorkflowStatus
