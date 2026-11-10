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

    attempts = 0
    max_attempts = 2
    execution = None
    last_exc = None

    while attempts < max_attempts:
        attempts += 1
        try:
            async with asyncio.timeout(budget.timeout_s):
                execution = await dependencies.execution.execute(state=state)
            if execution.get("success"):
                return {"execution": execution, "status": "executed"}
            if not execution.get("recoverable", True):
                break
        except Exception as exc:
            last_exc = exc
            if attempts >= max_attempts:
                break
            await asyncio.sleep(0.1)

    if execution is not None and execution.get("success"):
        return {"execution": execution, "status": "executed"}

    err_code = (
        (execution.get("error_code") if execution else None)
        or (last_exc.__class__.__name__ if last_exc else "execution_failed")
    )

    logger.warning(
        "execution failed after attempts",
        extra={
            "path": f"/workflows/{state['thread_id']}",
            "attempts": attempts,
            "error_code": err_code,
        },
    )
    return {
        "execution": execution or {
            "success": False,
            "error_code": err_code,
            "recoverable": True,
        },
        "status": "failed",
        "failure_reason": "execution_failed",
        "errors": [
            {
                "code": "execution_failed",
                "message": err_code,
                "node": "execute_tool",
            }
        ],
    }
