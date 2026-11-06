import asyncio
import logging

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)


async def supplier_lookup(state: ProcurementState) -> dict:
    dependencies = get_dependencies()
    try:
        async with asyncio.timeout(dependencies.supplier_timeout_seconds):
            candidates = await dependencies.suppliers.candidates(
                request=state["request"], as_of=state["as_of"]
            )
    except Exception as exc:
        logger.warning(
            "supplier lookup failed",
            extra={"path": f"/workflows/{state['thread_id']}"},
        )
        return {
            "supplier_results": [],
            "errors": [
                {
                    "code": "supplier_lookup_failed",
                    "message": exc.__class__.__name__,
                    "node": "supplier_lookup",
                }
            ],
        }

    return {"supplier_results": candidates}
