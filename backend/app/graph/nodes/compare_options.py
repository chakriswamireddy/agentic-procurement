import logging

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState
from app.services.comparison_service import ComparisonInputError

logger = logging.getLogger(__name__)


async def compare_options(state: ProcurementState) -> dict:
    dependencies = get_dependencies()
    try:
        comparison = dependencies.comparison.compare(
            state["request"],
            state.get("supplier_results") or [],
            as_of=state["as_of"],
        )
    except ComparisonInputError as exc:
        return {
            "status": "failed",
            "failure_reason": "comparison_failed",
            "errors": [
                {
                    "code": "comparison_failed",
                    "message": str(exc),
                    "node": "compare_options",
                }
            ],
        }

    update: dict = {"comparison": comparison}
    if not comparison.get("eligible"):
        update["status"] = "failed"
        update["failure_reason"] = "no_eligible_supplier"
    return update
