"""Table-driven tests for every conditional-routing branch (step 3.7)."""

import pytest
from app.graph.routing import (
    after_approval,
    after_execution,
    after_research,
    after_validate_request,
    after_validation,
)

FAN_OUT = ["supplier_lookup", "policy_retrieval"]


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
    ("errors", "expected"),
    [
        ([], "compare_options"),
        ([{"code": "supplier_lookup_failed"}], "compare_options"),
        ([{"code": "policy_retrieval_failed"}], "compare_options"),
        (
            [
                {"code": "supplier_lookup_failed"},
                {"code": "policy_retrieval_failed"},
            ],
            "record_result",
        ),
        (
            [
                {"code": "policy_retrieval_failed"},
                {"code": "supplier_lookup_failed"},
                {"code": "other"},
            ],
            "record_result",
        ),
    ],
)
def test_after_research(errors: list[dict], expected: str) -> None:
    assert after_research({"errors": errors}) == expected


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
