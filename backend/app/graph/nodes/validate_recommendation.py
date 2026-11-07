import logging

from app.agents.contracts import (
    ComparisonResult,
    PolicyEvidence,
    RequestFacts,
    ValidationRequest,
)
from app.agents.runner import run_specialist
from app.graph.dependencies import get_dependencies
from app.graph.state import ProcurementState

logger = logging.getLogger(__name__)


def _status_for(issues: list[dict]) -> tuple[str, str]:
    codes = {issue["code"] for issue in issues if issue.get("severity") == "blocking"}
    if not codes:
        return "awaiting_approval", ""
    if "missing_request_info" in codes:
        return "needs_info", "missing_request_info"
    if "no_eligible_supplier" in codes:
        return "failed", "no_eligible_supplier"
    if "weak_policy_evidence" in codes or "obsolete_evidence" in codes:
        return "inconclusive", "weak_policy_evidence"
    return "failed", "validation_failed"


def _evidence(state: ProcurementState) -> list[PolicyEvidence]:
    return [
        PolicyEvidence.from_dict(item) for item in state.get("policy_evidence") or []
    ]


async def validate_recommendation(state: ProcurementState) -> dict:
    """Thin adapter: persist, validate under budget, then explain without deciding."""
    dependencies = get_dependencies()
    budget = dependencies.budgets.for_node("validate_recommendation")
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

    result = await run_specialist(
        name="validate_recommendation",
        operation=lambda: dependencies.validator.validate(
            ValidationRequest(
                request=request,
                comparison=comparison,
                recommendation=recommendation,
                policy_status=policy_status,
                policy_evidence=tuple(_evidence(state)),
            )
        ),
        timeout_s=budget.timeout_s,
        max_attempts=budget.max_attempts,
        base_delay_s=dependencies.budgets.base_delay_s,
        max_delay_s=dependencies.budgets.max_delay_s,
        deadline_s=budget.deadline_s,
        correlation_id=state["correlation_id"],
        thread_id=state["thread_id"],
        metrics=dependencies.metrics,
    )

    if not result.ok:
        return {
            "status": "failed",
            "failure_reason": "validation_failed",
            "recommendation": recommendation,
            "errors": [result.to_error_entry(node="validate_recommendation")],
        }

    validation = result.data.to_dict() if result.data else {"sufficient": False, "issues": []}
    status, failure_reason = _status_for(list(validation["issues"]))
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

    if comparison and comparison.get("recommended"):
        try:
            update["explanation"] = await dependencies.explanation.explain(
                comparison=ComparisonResult.from_dict(comparison),
                evidence=_evidence(state),
                request=RequestFacts.from_request(request, as_of=state["as_of"]),
            )
        except Exception:  # an explanation must never break the workflow
            logger.warning(
                "explanation skipped",
                extra={
                    "path": f"/workflows/{state['thread_id']}",
                    "error_code": "explanation_failed",
                },
            )

    return update
