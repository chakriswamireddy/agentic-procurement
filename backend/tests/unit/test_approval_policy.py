"""Unit tests for Phase 5 Policy POL-002 approval rules."""

import pytest
from app.core.errors import ConflictError, ForbiddenError, ValidationError
from app.services.approval_policy_service import ApprovalPolicyService


def test_self_approval_prohibited() -> None:
    with pytest.raises(ForbiddenError, match="self_approval_prohibited"):
        ApprovalPolicyService.validate_approval(
            decision="approved",
            approver_id="USR0002",
            approver_role="approver",
            requester_id="USR0002",
            recommendation={"version": 1, "total_cost": "10000"},
        )


def test_unauthorized_role_rejected() -> None:
    with pytest.raises(ForbiddenError, match="not authorized to approve"):
        ApprovalPolicyService.validate_approval(
            decision="approved",
            approver_id="USR0003",
            approver_role="requester",  # requester cannot act as approver
            requester_id="USR0002",
            recommendation={"version": 1, "total_cost": "10000"},
        )


def test_rejection_requires_actionable_reason() -> None:
    with pytest.raises(ValidationError, match="rejection requires an actionable reason"):
        ApprovalPolicyService.validate_approval(
            decision="rejected",
            approver_id="USR0005",
            approver_role="approver",
            requester_id="USR0002",
            recommendation={"version": 1, "total_cost": "10000"},
            reason="",
        )


def test_stale_recommendation_version_raises_conflict() -> None:
    with pytest.raises(ConflictError, match="stale_recommendation_version"):
        ApprovalPolicyService.validate_approval(
            decision="approved",
            approver_id="USR0005",
            approver_role="approver",
            requester_id="USR0002",
            recommendation={"version": 2, "total_cost": "10000"},
            expected_version=1,  # Stale: client expected 1, but active is 2
        )


def test_valid_approval_succeeds() -> None:
    ApprovalPolicyService.validate_approval(
        decision="approved",
        approver_id="USR0005",
        approver_role="approver",
        requester_id="USR0002",
        recommendation={"version": 1, "total_cost": "45000"},
        reason="within standard band",
    )
