"""Table-driven tests for every conditional-routing branch (steps 3.7 and 4.9)."""

import pytest
from app.graph.routing import (
    after_approval,
    after_execution,
    after_research,
    after_validate_request,
    after_validation,
    research_outcome,
)

FAN_OUT = ["supplier_lookup", "policy_retrieval"]


def _errors(*nodes: str) -> list[dict]:
    return [{"code": f"{node}_failed", "node": node} for node in nodes]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("received", FAN_OUT),
        ("researching", FAN_OUT),
        ("needs_info", "record_result"),
        ("awaiting_approval", FAN_OUT),
    ],
)
def test_after_validate_request(status: str, expected) -> None:
    assert after_validate_request({"status": status}) == expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        # ok, non-empty | ok, conclusive -> compare
        ({}, "compare_options"),
        ({"errors": _errors("other")}, "compare_options"),
        # ok, empty | any -> compare (validation terminates with no_eligible_supplier)
        ({"supplier_results": []}, "compare_options"),
        # supplier failure alone -> failed / supplier_unavailable
        ({"errors": _errors("supplier_lookup")}, "record_result"),
        # policy failure alone -> inconclusive / policy_unavailable
        ({"errors": _errors("policy_retrieval")}, "record_result"),
        # both branches failed -> failed / research_unavailable
        (
            {"errors": _errors("supplier_lookup", "policy_retrieval")},
            "record_result",
        ),
        (
            {"errors": _errors("policy_retrieval", "supplier_lookup", "other")},
            "record_result",
        ),
        # ok, non-empty | inconclusive -> inconclusive / policy_evidence_insufficient
        (
            {"supplier_results": [{"supplier_id": "SUP0001"}],
             "policy_status": {"inconclusive": True}},
            "record_result",
        ),
        # supplier failure wins over an inconclusive policy flag
        (
            {"errors": _errors("supplier_lookup"),
             "policy_status": {"inconclusive": True}},
            "record_result",
        ),
    ],
)
def test_after_research(state: dict, expected: str) -> None:
    assert after_research(state) == expected


@pytest.mark.parametrize(
    ("state", "status", "failure_reason"),
    [
        ({"errors": _errors("supplier_lookup")}, "failed", "supplier_unavailable"),
        ({"errors": _errors("policy_retrieval")}, "inconclusive", "policy_unavailable"),
        (
            {"errors": _errors("supplier_lookup", "policy_retrieval")},
            "failed",
            "research_unavailable",
        ),
        (
            {
                "supplier_results": [{"supplier_id": "SUP0001"}],
                "policy_status": {"inconclusive": True},
            },
            "inconclusive",
            "policy_evidence_insufficient",
        ),
        ({"supplier_results": []}, None, None),
    ],
)
def test_research_outcome_matrix(state: dict, status, failure_reason) -> None:
    outcome = research_outcome(state)
    assert outcome.route == (
        "record_result" if status is not None else "compare_options"
    )
    assert outcome.status == status
    assert outcome.failure_reason == failure_reason


@pytest.mark.parametrize(
    ("validation", "expected"),
    [
        ({"sufficient": True}, "approval_interrupt"),
        ({"sufficient": False}, "record_result"),
        ({}, "record_result"),
        (None, "record_result"),
    ],
)
def test_after_validation(validation, expected: str) -> None:
    state = {} if validation is None else {"validation": validation}
    assert after_validation(state) == expected


@pytest.mark.parametrize(
    ("approval", "expected"),
    [
        ({"valid": True, "decision": "approved"}, "execute_tool"),
        ({"valid": True, "decision": "rejected"}, "record_result"),
        ({"valid": False, "decision": "approved"}, "record_result"),
        ({"valid": False}, "record_result"),
        ({}, "record_result"),
        (None, "record_result"),
    ],
)
def test_after_approval(approval, expected: str) -> None:
    state = {} if approval is None else {"approval": approval}
    assert after_approval(state) == expected


def test_after_execution_always_records() -> None:
    assert after_execution({"status": "executed"}) == "record_result"
    assert after_execution({"status": "failed"}) == "record_result"
