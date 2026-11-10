"""Unit tests for resource-level authorization helpers (Phase 5.5)."""

import pytest
from app.core.authz import (
    ensure_can_approve,
    ensure_can_create_request,
    ensure_can_manage_documents,
    ensure_can_retry_execution,
    ensure_request_read,
)
from app.core.errors import ForbiddenError, NotFoundError
from app.schemas.auth import AuthenticatedUser


def _user(role: str, user_id: str = "USR1") -> AuthenticatedUser:
    return AuthenticatedUser(id=user_id, email=f"{user_id}@x.test", role=role)


class Rec:
    def __init__(self, requester_id: str) -> None:
        self.requester_id = requester_id


def test_requester_reads_own_only() -> None:
    user = _user("requester", "USR2")
    ensure_request_read(user, Rec("USR2"))  # ok
    with pytest.raises(NotFoundError):
        ensure_request_read(user, Rec("USR9"))


def test_privileged_roles_read_any() -> None:
    for role in ("approver", "admin", "auditor"):
        ensure_request_read(_user(role), Rec("USR9"))


def test_self_approval_blocked_for_admin() -> None:
    admin = _user("admin", "USR1")
    with pytest.raises(ForbiddenError, match="self_approval_prohibited"):
        ensure_can_approve(admin, Rec("USR1"))


def test_non_approver_role_blocked() -> None:
    with pytest.raises(ForbiddenError, match="not permitted"):
        ensure_can_approve(_user("requester", "USR2"), Rec("USR9"))
    with pytest.raises(ForbiddenError, match="not permitted"):
        ensure_can_approve(_user("auditor", "USR15"), Rec("USR9"))


def test_approver_can_approve_others() -> None:
    ensure_can_approve(_user("approver", "USR5"), Rec("USR2"))
    ensure_can_approve(_user("admin", "USR1"), Rec("USR2"))


def test_document_management_admin_only() -> None:
    ensure_can_manage_documents(_user("admin"))
    with pytest.raises(ForbiddenError):
        ensure_can_manage_documents(_user("approver"))
    with pytest.raises(ForbiddenError):
        ensure_can_manage_documents(_user("requester"))


def test_create_request_roles() -> None:
    ensure_can_create_request(_user("requester"))
    ensure_can_create_request(_user("admin"))
    with pytest.raises(ForbiddenError):
        ensure_can_create_request(_user("auditor"))
    with pytest.raises(ForbiddenError):
        ensure_can_create_request(_user("approver"))


def test_retry_execution_roles() -> None:
    ensure_can_retry_execution(_user("admin"))
    ensure_can_retry_execution(_user("approver"))
    with pytest.raises(ForbiddenError):
        ensure_can_retry_execution(_user("requester"))
