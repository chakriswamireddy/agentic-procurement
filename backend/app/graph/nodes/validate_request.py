import logging

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)


async def validate_request(state: ProcurementState) -> dict:
    result = get_dependencies().request_validator.validate(state["request"])
    if not result["valid"]:
        logger.info(
            "procurement request needs information",
            extra={"path": f"/workflows/{state['thread_id']}"},
        )
        return {
            "status": "needs_info",
            "failure_reason": "invalid_request",
            "errors": [
                {**issue, "node": "validate_request"} for issue in result["issues"]
            ],
        }
    return {"status": "researching"}
