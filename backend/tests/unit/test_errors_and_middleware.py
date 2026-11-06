from app.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.middleware import sanitize_request_id


def test_error_status_mapping() -> None:
    assert NotFoundError().status_code == 404
    assert ValidationError().status_code == 422
    assert ConflictError().status_code == 409
    assert DependencyUnavailableError().status_code == 503
    assert UnauthorizedError().status_code == 401
    assert ForbiddenError().status_code == 403


def test_error_keeps_custom_message() -> None:
    error = NotFoundError("supplier SUP9999 not found")

    assert error.message == "supplier SUP9999 not found"
    assert error.code == "not_found"


def test_request_id_is_accepted_when_safe() -> None:
    assert sanitize_request_id("test-123") == "test-123"
    assert sanitize_request_id("a" * 64) == "a" * 64


def test_request_id_is_rejected_when_invalid() -> None:
    assert sanitize_request_id(None) is None
    assert sanitize_request_id("short") is None
    assert sanitize_request_id("bad id with spaces") is None
    assert sanitize_request_id("x" * 500) is None
    assert sanitize_request_id("<script>alert(1)</script>") is None
