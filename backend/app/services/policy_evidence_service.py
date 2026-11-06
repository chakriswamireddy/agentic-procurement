"""Deterministic policy evidence adapter used by the workflow graph."""

from datetime import date
from typing import Any

from app.services.policy_service import PolicyService
from app.services.recommendation_service import build_policy_query


class PolicyEvidenceService:
    def __init__(self, policy_service: PolicyService) -> None:
        self.policy_service = policy_service

    async def evidence_for(
        self, *, request: dict[str, Any], as_of: str
    ) -> dict[str, Any]:
        query = build_policy_query(request)
        response = await self.policy_service.search(
            query,
            as_of=date.fromisoformat(as_of),
        )
        return {
            "query": query,
            "inconclusive": response.inconclusive,
            "reason": response.reason,
            "evidence": [
                item.model_dump(mode="json") for item in response.evidence
            ],
        }
