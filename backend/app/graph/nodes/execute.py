import asyncio
import logging

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)


async def execute_tool(state: ProcurementState) -> dict:
    """Purchase execution is non-idempotent: budgeted, but never retried generically.

    Phase 5 adds idempotent retry on top of the execution gateway; the generic
    specialist runner must not retry this node.
    """
    dependencies = get_dependencies()
    budget = dependencies.budgets.for_node("execute_tool")

    approval = state.get("approval") or {}
    if not approval.get("valid") or approval.get("decision") != "approved":
        return {
            "status": "failed",
            "failure_reason": "execution_without_approval",
            "errors": [
                {
                    "code": "execution_without_approval",
                    "message": "execution requires a valid approved decision",
                    "node": "execute_tool",
                }
            ],
        }

    try:
        async with asyncio.timeout(budget.timeout_s):
            execution = await dependencies.execution.execute(state=state)
    except Exception as exc:
        logger.exception(
            "execution failed",
            extra={"path": f"/workflows/{state['thread_id']}"},
        )
        return {
            "execution": {
                "success": False,
                "error_code": exc.__class__.__name__,
                "recoverable": True,
            },
            "status": "failed",
            "failure_reason": "execution_failed",
            "errors": [
                {
                    "code": "execution_failed",
                    "message": exc.__class__.__name__,
                    "node": "execute_tool",
                }
            ],
        }

    if execution.get("success"):
        return {"execution": execution, "status": "executed"}

    return {
        "execution": execution,
        "status": "failed",
        "failure_reason": "execution_failed",
        "errors": [
            {
                "code": "execution_failed",
                "message": execution.get("error_code") or "execution failed",
                "node": "execute_tool",
            }
        ],
    }
