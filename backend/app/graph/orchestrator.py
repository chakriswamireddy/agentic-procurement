"""The orchestrator: topology, budgets, routing, termination, and the plan trace.

The orchestrator in this project is the graph topology plus routing and budgets — not a
free-roaming LLM. That keeps the workflow path inspectable, testable, and bounded.

It owns:

- the workflow topology (which capabilities run, in what order);
- budget allocation (per-call timeouts, attempts, node deadlines, candidate/evidence caps);
- routing decisions after research and validation;
- termination: success, needs_info, inconclusive, failed, rejected, executed;
- recording a plan/decision trace (``state["plan"]``) for inspection.

It never invents supplier facts, scores suppliers, approves or executes purchases, calls
arbitrary tools chosen by an LLM, or loops indefinitely.

Why not autonomous agents? The requirements are known and bounded. Independent loops add
nondeterminism, cost, and debugging difficulty without a demonstrated need. Specialists
are ordinary services behind graph nodes; the graph is the supervisor. Revisit this only
if a demonstrated requirement needs open-ended supplier discovery, heterogeneous tools
with unknown sequencing, or genuinely dynamic planning.

Loop prevention is explicit: the graph recursion limit (settings
``workflow_recursion_limit``, default 25), the runner's hard attempt cap of 3, no
node-to-node calls (all transitions are edges), no self-handoff, and terminal states that
always end the run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import Settings

TERMINAL_STATUSES = frozenset(
    {"needs_info", "inconclusive", "failed", "rejected", "executed"}
)
RESEARCH_CAPABILITIES = ("supplier", "policy")
DEFAULT_RECURSION_LIMIT = 25
MAX_SPECIALIST_ATTEMPTS = 3
SUPERVISOR_MAX_ITERATIONS = 6
PLAN_REASON = "standard_request"


@dataclass(frozen=True)
class NodeBudget:
    """Timeout, retry, and deadline budget for one graph node."""

    node: str
    timeout_s: float
    max_attempts: int
    deadline_s: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowBudgets:
    """All workflow budgets in one place so nothing hard-codes a number twice."""

    supplier_lookup: NodeBudget
    policy_retrieval: NodeBudget
    compare_options: NodeBudget
    validate_recommendation: NodeBudget
    execute_tool: NodeBudget
    base_delay_s: float
    max_delay_s: float
    max_candidates: int
    max_evidence: int

    def for_node(self, node: str) -> NodeBudget:
        budgets = {
            "supplier_lookup": self.supplier_lookup,
            "policy_retrieval": self.policy_retrieval,
            "compare_options": self.compare_options,
            "validate_recommendation": self.validate_recommendation,
            "execute_tool": self.execute_tool,
        }
        try:
            return budgets[node]
        except KeyError as exc:
            raise KeyError(f"no budget defined for node {node!r}") from exc

    def as_dict(self) -> dict[str, Any]:
        return {node: budget.as_dict() for node, budget in self.for_node_all()}

    def for_node_all(self) -> list[tuple[str, NodeBudget]]:
        return [
            ("supplier_lookup", self.supplier_lookup),
            ("policy_retrieval", self.policy_retrieval),
            ("compare_options", self.compare_options),
            ("validate_recommendation", self.validate_recommendation),
            ("execute_tool", self.execute_tool),
        ]


def budgets_from_settings(settings: Settings) -> WorkflowBudgets:
    """Build budgets from settings; nodes must never hard-code their own numbers."""
    research_deadline = settings.workflow_research_deadline_seconds
    single_attempt_deadline_multiplier = 2.0
    return WorkflowBudgets(
        supplier_lookup=NodeBudget(
            node="supplier_lookup",
            timeout_s=settings.workflow_supplier_timeout_seconds,
            max_attempts=settings.workflow_specialist_max_attempts,
            deadline_s=research_deadline,
        ),
        policy_retrieval=NodeBudget(
            node="policy_retrieval",
            timeout_s=settings.workflow_policy_timeout_seconds,
            max_attempts=settings.workflow_specialist_max_attempts,
            deadline_s=research_deadline,
        ),
        compare_options=NodeBudget(
            node="compare_options",
            timeout_s=settings.workflow_compare_timeout_seconds,
            max_attempts=1,
            deadline_s=settings.workflow_compare_timeout_seconds
            * single_attempt_deadline_multiplier,
        ),
        validate_recommendation=NodeBudget(
            node="validate_recommendation",
            timeout_s=settings.workflow_validate_timeout_seconds,
            max_attempts=1,
            deadline_s=settings.workflow_validate_timeout_seconds
            * single_attempt_deadline_multiplier,
        ),
        execute_tool=NodeBudget(
            node="execute_tool",
            timeout_s=settings.workflow_execute_timeout_seconds,
            max_attempts=1,
            deadline_s=settings.workflow_execute_deadline_seconds,
        ),
        base_delay_s=settings.workflow_specialist_base_delay_seconds,
        max_delay_s=settings.workflow_specialist_max_delay_seconds,
        max_candidates=settings.workflow_max_supplier_candidates,
        max_evidence=settings.workflow_max_policy_evidence,
    )


def build_plan(
    budgets: WorkflowBudgets, *, reason: str = PLAN_REASON
) -> dict[str, Any]:
    """Record the static plan: capabilities, budgets, and why this plan applies.

    The topology stays static in phase 4 — the plan documents intent and budgets, it
    never spawns arbitrary agents.
    """
    return {
        "research": list(RESEARCH_CAPABILITIES),
        "budgets": {
            "supplier_timeout_s": budgets.supplier_lookup.timeout_s,
            "policy_timeout_s": budgets.policy_retrieval.timeout_s,
            "supplier_attempts": budgets.supplier_lookup.max_attempts,
            "policy_attempts": budgets.policy_retrieval.max_attempts,
            "research_deadline_s": budgets.supplier_lookup.deadline_s,
            "max_candidates": budgets.max_candidates,
            "max_evidence": budgets.max_evidence,
        },
        "reason": reason,
    }
