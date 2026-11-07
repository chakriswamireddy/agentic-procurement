from app.graph.routing import research_outcome
from app.graph.state import ProcurementState


async def research_join(state: ProcurementState) -> dict:
    """Fan-in gate. Runs after both research branches finish.

    Applies the partial-failure matrix: if research must terminate, the terminal status
    and failure reason are recorded here so routing and state can never disagree.
    """
    outcome = research_outcome(state)
    if outcome.route == "record_result":
        return {
            "status": outcome.status,
            "failure_reason": outcome.failure_reason,
        }
    return {}
