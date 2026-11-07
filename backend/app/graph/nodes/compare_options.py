import logging

from app.agents.contracts import ComparisonRequest
from app.agents.runner import run_specialist
from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)


async def compare_options(state: ProcurementState) -> dict:
    """Thin adapter around the deterministic analysis specialist."""
    dependencies = get_dependencies()
    budget = dependencies.budgets.for_node("compare_options")

    result = await run_specialist(
        name="compare_options",
        operation=lambda: dependencies.comparison.compare(
            ComparisonRequest.from_state(
                request=state["request"],
                candidates=state.get("supplier_results") or [],
                as_of=state["as_of"],
            )
        ),
        timeout_s=budget.timeout_s,
        max_attempts=budget.max_attempts,
        base_delay_s=dependencies.budgets.base_delay_s,
        max_delay_s=dependencies.budgets.max_delay_s,
        deadline_s=budget.deadline_s,
        correlation_id=state["correlation_id"],
        thread_id=state["thread_id"],
        metrics=dependencies.metrics,
    )

    if not result.ok:
        return {
            "status": "failed",
            "failure_reason": "comparison_failed",
            "errors": [result.to_error_entry(node="compare_options")],
        }

    comparison = (result.data.to_dict() if result.data else {})
    update: dict = {"comparison": comparison}
    if not comparison.get("eligible"):
        update["status"] = "failed"
        update["failure_reason"] = "no_eligible_supplier"
    return update
