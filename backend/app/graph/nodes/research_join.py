from app.graph.state import ProcurementState


async def research_join(state: ProcurementState) -> dict:
    """Fan-in gate. LangGraph runs this after both research branches finish."""
    del state
    return {}
