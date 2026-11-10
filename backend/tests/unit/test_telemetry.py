"""Tests for structured telemetry and sensitive data redaction (Phase 6, Step 6.4)."""


from app.core.logging import correlation_id_var
from app.core.telemetry import (
    WorkflowTelemetry,
    anonymize_user_id,
    init_tracing,
    recursive_redact,
)


def test_recursive_redact_sensitive_keys():
    payload = {
        "user_email": "procurement@example.com",
        "auth": {
            "password": "supersecretpassword123",
            "api_key": "sk-1234567890abcdef",
            "jwt_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "authorization_header": "Bearer secret-token",
        },
        "nested_list": [
            {"access_token": "token-abc"},
            {"public_info": "safe_data"},
        ],
        "database_url": "postgresql://procurement:mypassword@localhost:5432/db",
    }

    sanitized = recursive_redact(payload)

    # Secrets must be scrubbed
    assert sanitized["auth"]["password"] == "***"
    assert sanitized["auth"]["api_key"] == "***"
    assert sanitized["auth"]["jwt_token"] == "***"
    assert sanitized["auth"]["authorization_header"] == "***"
    assert sanitized["nested_list"][0]["access_token"] == "***"
    assert sanitized["nested_list"][1]["public_info"] == "safe_data"
    assert "mypassword" not in sanitized["database_url"]
    assert "postgresql://procurement:***@localhost:5432/db" == sanitized["database_url"]


def test_recursive_redact_truncates_large_payloads():
    huge_string = "A" * 1000
    sanitized = recursive_redact({"text": huge_string}, max_string_len=100)
    assert len(sanitized["text"]) < 200
    assert "... [truncated 900 chars]" in sanitized["text"]


def test_anonymize_user_id():
    raw_user_id = "USR0001"
    hashed = anonymize_user_id(raw_user_id)
    assert hashed != raw_user_id
    assert len(hashed) == 12
    # Deterministic
    assert anonymize_user_id(raw_user_id) == hashed
    assert anonymize_user_id(None) is None


def test_workflow_telemetry_emit_event():
    correlation_id_var.set("test-corr-id-1234")

    event = WorkflowTelemetry.emit_node_transition(
        node_name="validate_request",
        thread_id="thread-abc",
        request_id="req-xyz",
        user_id="USR0002",
        duration_ms=45.2,
        outcome="success",
        chunk_ids=["chunk1", "chunk2"],
        extra={"password": "should_be_hidden", "status": "ok"},
    )

    assert event["service"] == "agentic-procurement"
    assert event["correlation_id"] == "test-corr-id-1234"
    assert event["node"] == "validate_request"
    assert event["outcome"] == "success"
    assert event["duration_ms"] == 45.2
    assert event["user_id_hash"] is not None
    assert event["chunk_count"] == 2
    assert event["details"]["password"] == "***"
    assert event["details"]["status"] == "ok"


def test_init_tracing_safely_noops():
    # LangSmith tracing disabled: should safely return without exceptions
    init_tracing(enabled=False)
    # LangSmith enabled without API key: should not raise
    init_tracing(enabled=True)
