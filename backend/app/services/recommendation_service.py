"""Deterministic policy query and recommendation assembly."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.repositories.recommendation_repository import RecommendationRepository
from app.services.scoring_config import SCORING_VERSION

MAX_POLICY_QUERY_CHARS = 300


def build_policy_query(request: dict[str, Any]) -> str:
    """Build a short, deterministic policy query. Never call an LLM here."""
    constraints = request.get("constraints") or {}
    max_delivery = constraints.get("max_delivery_days")
    certifications = constraints.get("required_certifications") or []
    parts = [
        str(request.get("product_name", "")).strip(),
        str(request.get("category", "")).strip(),
        "procurement approval threshold",
        f"quantity {request.get('quantity', '')}",
        f"delivery {max_delivery if max_delivery is not None else 'standard'}",
        "certifications "
        + (" ".join(sorted(str(value) for value in certifications)) if certifications else "none"),
    ]
    query = " ".join(part for part in parts if part)
    return " ".join(query.split())[:MAX_POLICY_QUERY_CHARS]


def _caveats(comparison: dict[str, Any], issues: list[dict[str, Any]]) -> list[str]:
    recommended = comparison.get("recommended") or {}
    caveats: list[str] = []
    if recommended.get("valid_until"):
        caveats.append(f"price valid until {recommended['valid_until']}")
    if recommended.get("risk_level"):
        caveats.append(f"risk level: {recommended['risk_level']}")
    for issue in issues:
        if issue.get("severity") != "blocking" and issue.get("message"):
            caveats.append(str(issue["message"]))
    return caveats


class RecommendationService:
    def __init__(self, recommendations: RecommendationRepository) -> None:
        self.recommendations = recommendations

    async def prepare_and_persist(
        self,
        *,
        request: dict[str, Any],
        comparison: dict[str, Any],
        policy_evidence: list[dict[str, Any]],
        policy_query: str,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        recommended = comparison.get("recommended")
        if not recommended:
            return None

        request_id = str(request["request_id"])
        version = await self.recommendations.next_version(request_id)
        rationale = {
            "scoring_version": SCORING_VERSION,
            "comparison": comparison.get("rationale", {}),
            "caveats": _caveats(comparison, issues),
            "policy_query": policy_query,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        recommendation = {
            "supplier_id": recommended["supplier_id"],
            "supplier_name": recommended["supplier_name"],
            "score": recommended["total_score"],
            "scoring_version": SCORING_VERSION,
            "total_cost": recommended["total_cost"],
            "unit_price": recommended["unit_price"],
            "currency": recommended["currency"],
            "delivery_days": recommended["delivery_days"],
            "valid_until": recommended["valid_until"],
            "risk_level": recommended["risk_level"],
            "rationale": rationale,
            "evidence": policy_evidence,
            "evidence_query": policy_query,
            "caveats": rationale["caveats"],
            "version": version,
            "persisted": False,
        }

        record = await self.recommendations.create(
            request_id=request_id,
            supplier_id=recommendation["supplier_id"],
            score=Decimal(recommendation["score"]),
            rationale=rationale,
            evidence={"query": policy_query, "items": policy_evidence},
            version=version,
        )
        await self.recommendations.session.commit()
        recommendation["id"] = record.id
        recommendation["persisted"] = True
        return recommendation

    async def is_persisted(self, request_id: str, version: int) -> bool:
        record = await self.recommendations.get_by_version(request_id, version)
        return record is not None
