"""Pure routing functions and the partial-failure matrix (phase 4, step 4.9).

No I/O and no mutation. The research matrix decides, after the parallel branches fan in,
whether the workflow may continue to comparison or must terminate with a safe
user-visible outcome:

| Supplier result       | Policy result     | Route    | User-visible outcome         |
|-----------------------|-------------------|----------|------------------------------|
| ok, non-empty         | ok, conclusive    | compare  | recommendation               |
| ok, empty             | any               | compare  | no_eligible_supplier         |
| transient failure     | ok                | terminal | supplier_unavailable         |
| ok, non-empty         | inconclusive      | terminal | policy_evidence_insufficient |
| ok, non-empty         | transient failure | terminal | policy_unavailable           |
| failure               | failure           | terminal | research_unavailable         |
| permanent valid. issue| any               | validate | specific reason (step 3.5)   |

Rules: never continue to approval when policy evidence is missing, never continue with
zero eligible suppliers, never substitute stale data, and keep "no supplier matches"
(a business outcome) distinct from "supplier service down" (an operational failure).
"""

from dataclasses import dataclass
from typing import Literal

from app.graph.state import ProcurementState

Route = Literal[
    "supplier_lookup",
    "policy_retrieval",
    "compare_options",
    "approval_interrupt",
    "execute_tool",
    "record_result",
]

RESEARCH_NODES = ("supplier_lookup", "policy_retrieval")


@dataclass(frozen=True)
class ResearchOutcome:
    """Where research sends the workflow, and the terminal status if it stops there."""

    route: Literal["compare_options", "record_result"]
    status: str | None = None
    failure_reason: str | None = None


def _branch_failed(state: ProcurementState, node: str) -> bool:
    return any(error.get("node") == node for error in state.get("errors") or [])


def research_outcome(state: ProcurementState) -> ResearchOutcome:
    """Evaluate the partial-failure matrix for the fan-in state."""
    supplier_failed = _branch_failed(state, "supplier_lookup")
    policy_failed = _branch_failed(state, "policy_retrieval")
    policy_status = state.get("policy_status") or {}
    candidates = state.get("supplier_results")

    if supplier_failed and policy_failed:
        return ResearchOutcome("record_result", "failed", "research_unavailable")
    if supplier_failed:
        return ResearchOutcome("record_result", "failed", "supplier_unavailable")
    if candidates is not None and len(candidates) == 0:
        # Business outcome, not an operational failure: comparison still runs so the
        # audit trail records the empty candidate set, then validation terminates it.
        return ResearchOutcome("compare_options")
    if policy_failed:
        return ResearchOutcome("record_result", "inconclusive", "policy_unavailable")
    if policy_status.get("inconclusive"):
        return ResearchOutcome(
            "record_result", "inconclusive", "policy_evidence_insufficient"
        )
    return ResearchOutcome("compare_options")


def after_validate_request(state: ProcurementState) -> list[str] | str:
    if state.get("status") == "needs_info":
        return "record_result"
    return ["supplier_lookup", "policy_retrieval"]


def after_research(state: ProcurementState) -> str:
    return research_outcome(state).route


def after_validation(state: ProcurementState) -> str:
    validation = state.get("validation") or {}
    if validation.get("sufficient"):
        return "approval_interrupt"
    return "record_result"


def after_approval(state: ProcurementState) -> str:
    approval = state.get("approval") or {}
    if not approval.get("valid"):
        return "record_result"
    if approval.get("decision") == "approved":
        return "execute_tool"
    return "record_result"


def after_execution(state: ProcurementState) -> str:
    del state
    return "record_result"
