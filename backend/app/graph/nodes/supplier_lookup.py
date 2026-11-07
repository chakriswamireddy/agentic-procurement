import logging

from app.agents.contracts import SupplierQuery
from app.agents.runner import run_specialist
from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)


async def supplier_lookup(state: ProcurementState) -> dict:
    """Thin adapter: extract DTO, call the specialist under budget, map to state."""
    dependencies = get_dependencies()
    budget = dependencies.budgets.for_node("supplier_lookup")
    query = SupplierQuery.from_request(state["request"], as_of=state["as_of"])

    result = await run_specialist(
        name="supplier_lookup",
        operation=lambda: dependencies.suppliers.search(query),
        timeout_s=budget.timeout_s,
        max_attempts=budget.max_attempts,
        base_delay_s=dependencies.budgets.base_delay_s,
        max_delay_s=dependencies.budgets.max_delay_s,
        deadline_s=budget.deadline_s,
        correlation_id=state["correlation_id"],
        thread_id=state["thread_id"],
        timeout_code="supplier_timeout",
        metrics=dependencies.metrics,
        source_ids_of=lambda data: tuple(item.quotation_id for item in data),
    )

    if not result.ok:
        logger.warning(
            "supplier lookup failed",
            extra={"path": f"/workflows/{state['thread_id']}"},
        )
        return {
            "supplier_results": [],
            "errors": [result.to_error_entry(node="supplier_lookup")],
        }

    return {
        "supplier_results": [
            candidate.to_dict() for candidate in (result.data or [])
        ]
    }
