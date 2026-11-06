import asyncio
import logging

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState
from app.services.recommendation_service import build_policy_query

logger = logging.getLogger(__name__)


async def policy_retrieval(state: ProcurementState) -> dict:
    dependencies = get_dependencies()
    query = build_policy_query(state["request"])
    try:
        async with asyncio.timeout(dependencies.policy_timeout_seconds):
            result = await dependencies.policies.evidence_for(
                request=state["request"], as_of=state["as_of"]
            )
    except Exception as exc:
        logger.warning(
            "policy retrieval failed",
            extra={"path": f"/workflows/{state['thread_id']}"},
        )
        return {
            "policy_evidence": [],
            "policy_status": {
                "query": query,
                "inconclusive": True,
                "reason": "dependency_unavailable",
            },
            "errors": [
                {
                    "code": "policy_retrieval_failed",
                    "message": exc.__class__.__name__,
                    "node": "policy_retrieval",
                }
            ],
        }

    return {
        "policy_evidence": result.get("evidence") or [],
        "policy_status": {
            "query": result.get("query", query),
            "inconclusive": bool(result.get("inconclusive")),
            "reason": result.get("reason"),
        },
    }
