"""Resource-level authorization helpers (Phase 5).

Role checks alone are not enough: a requester must only read their own
requests, and an approver must never approve their own request (POL-002).
Failures raise 403/404 without leaking whether a resource exists.
"""

from typing import Any, Protocol

from app.core.errors import ForbiddenError, NotFoundError
from app.schemas.auth import AuthenticatedUser


class RequestRecord(Protocol):
    requester_id: str


def ensure_request_read(user: AuthenticatedUser, record: Any) -> None:
    """Requester reads only their own request; privileged roles read any."""
    if user.role == "requester" and record.requester_id != user.id:
        # 404 avoids resource-id enumeration by other tenants.
        raise NotFoundError("procurement request not found")


def ensure_can_approve(user: AuthenticatedUser, record: Any) -> None:
    """Approver/admin may approve only requests they did not create (POL-002)."""
    if record.requester_id == user.id:
        raise ForbiddenError(
            "self_approval_prohibited: requesters cannot approve their own requests"
        )
    if user.role not in ("approver", "admin"):
        raise ForbiddenError(f"role {user.role} is not permitted to approve")


def ensure_can_manage_documents(user: AuthenticatedUser) -> None:
    """Document upload/ingest is admin-only (MVP)."""
    if user.role != "admin":
        raise ForbiddenError(f"role {user.role} is not permitted to manage documents")


def ensure_can_create_request(user: AuthenticatedUser) -> None:
    if user.role not in ("requester", "admin"):
        raise ForbiddenError(
            f"role {user.role} is not permitted to create procurement requests"
        )


def ensure_can_retry_execution(user: AuthenticatedUser) -> None:
    if user.role not in ("admin", "approver"):
        raise ForbiddenError(
            f"role {user.role} is not permitted to retry execution"
        )
