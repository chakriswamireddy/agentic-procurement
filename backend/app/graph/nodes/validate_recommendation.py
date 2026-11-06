import logging

from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)

_BLOCKING_CODES = {
    "missing_request_info",
    "no_eligible_supplier",
    "recommendation_missing",
    "recommendation_not_eligible",
    "recommendation_not_persisted",
    "invalid_recommendation_version",
    "score_mismatch",
    "total_cost_mismatch",
    "constraint_violation",
    "weak_policy_evidence",
    "evidence_missing_fields",
    "obsolete_evidence",
}


def _status_for(issues: list[dict]) -> tuple[str, str]:
    codes = {issue["code"] for issue in issues if issue.get("severity") == "blocking"}
    if not codes:
        return "awaiting_approval", ""
    if "missing_request_info" in codes:
        return "needs_info", "missing_request_info"
    if "weak_policy_evidence" in codes or "obsolete_evidence" in codes:
        return "inconclusive", "weak_policy_evidence"
    if "no_eligible_supplier" in codes:
        return "failed", "no_eligible_supplier"
    return "failed", "validation_failed"


async def validate_recommendation(state: ProcurementState) -> dict:
    dependencies = get_dependencies()
    request = state["request"]
    comparison = state.get("comparison")
    policy_status = state.get("policy_status") or {}
    policy_evidence = state.get("policy_evidence") or []

    recommendation = None
    if comparison and comparison.get("recommended"):
        recommendation = await dependencies.recommendations.prepare_and_persist(
            request={**request, "request_id": state["request_id"]},
            comparison=comparison,
            policy_evidence=policy_evidence,
            policy_query=policy_status.get("query", ""),
            issues=[],
        )

    validation = dependencies.validator.validate(
        request=request,
        comparison=comparison,
        recommendation=recommendation,
        policy_status=policy_status,
        policy_evidence=policy_evidence,
    )

    status, failure_reason = _status_for(validation["issues"])
    update: dict = {"validation": validation, "recommendation": recommendation}
    update["status"] = status
    if failure_reason:
        update["failure_reason"] = failure_reason

    blocking = [
        {**issue, "node": "validate_recommendation"}
        for issue in validation["issues"]
        if issue.get("severity") == "blocking"
    ]
    if blocking:
        update["errors"] = blocking
        logger.info(
            "recommendation validation blocked workflow",
            extra={
                "path": f"/workflows/{state['thread_id']}",
                "status": status,
            },
        )
    return update
