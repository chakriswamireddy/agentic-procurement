import logging

from app.agents.contracts import PolicyQuery
from app.agents.runner import run_specialist
from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState
from app.services.recommendation_service import build_policy_query

logger = logging.getLogger(__name__)


async def policy_retrieval(state: ProcurementState) -> dict:
    """Thin adapter: extract DTO, call the specialist under budget, map to state."""
    dependencies = get_dependencies()
    budget = dependencies.budgets.for_node("policy_retrieval")
    query = PolicyQuery(
        text=build_policy_query(state["request"]),
        as_of=state["as_of"],
        limit=dependencies.budgets.max_evidence,
    )

    result = await run_specialist(
        name="policy_retrieval",
        operation=lambda: dependencies.policies.retrieve(query),
        timeout_s=budget.timeout_s,
        max_attempts=budget.max_attempts,
        base_delay_s=dependencies.budgets.base_delay_s,
        max_delay_s=dependencies.budgets.max_delay_s,
        deadline_s=budget.deadline_s,
        correlation_id=state["correlation_id"],
        thread_id=state["thread_id"],
        timeout_code="policy_timeout",
        metrics=dependencies.metrics,
    )

    if not result.ok:
        logger.warning(
            "policy retrieval failed",
            extra={"path": f"/workflows/{state['thread_id']}"},
        )
        return {
            "policy_evidence": [],
            "policy_status": {
                "query": query.text,
                "inconclusive": True,
                "reason": "dependency_unavailable",
            },
            "errors": [result.to_error_entry(node="policy_retrieval")],
        }

    payload = result.data.to_state()
    return {
        "policy_evidence": payload["evidence"],
        "policy_status": {
            "query": payload["query"],
            "inconclusive": payload["inconclusive"],
            "reason": payload["reason"],
        },
    }
