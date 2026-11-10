"""Structured telemetry, sensitive data redaction, and optional tracing (Phase 6, Step 6.4)."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_correlation_id

logger = logging.getLogger("app.telemetry")

REDACTED_MARKER = "***"
SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|secret|token|api[_-]?key|jwt|authorization|credential|bearer)",
    re.IGNORECASE,
)
URL_CREDENTIAL_PATTERN = re.compile(r"://([^:@]+):([^@]+)@")


def recursive_redact(data: Any, *, max_string_len: int = 500) -> Any:
    """Recursively scrub sensitive keys, tokens, and PII from telemetry dictionaries."""
    if isinstance(data, dict):
        scrubbed = {}
        for key, value in data.items():
            if isinstance(key, str) and SENSITIVE_KEY_PATTERNS.search(key):
                scrubbed[key] = REDACTED_MARKER
            else:
                scrubbed[key] = recursive_redact(value, max_string_len=max_string_len)
        return scrubbed
    elif isinstance(data, (list, tuple, set)):
        items = [recursive_redact(item, max_string_len=max_string_len) for item in data]
        return type(data)(items) if not isinstance(data, set) else set(items)
    elif isinstance(data, str):
        # Redact embedded credentials in URLs
        if "://" in data and "@" in data:
            data = URL_CREDENTIAL_PATTERN.sub(r"://\1:***@", data)
        # Truncate overly long text payloads (e.g. raw policy markdown)
        if len(data) > max_string_len:
            return data[:max_string_len] + f"... [truncated {len(data) - max_string_len} chars]"
        return data
    return data


def anonymize_user_id(user_id: str | None) -> str | None:
    """Hash user ID to prevent PII exposure in downstream telemetry and log aggregates."""
    if not user_id:
        return None
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


class WorkflowTelemetry:
    """Recorder for workflow node transitions and audit telemetry."""

    SERVICE_NAME = "agentic-procurement"

    @classmethod
    def emit_node_transition(
        cls,
        *,
        node_name: str,
        thread_id: str | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
        duration_ms: float | None = None,
        outcome: str = "success",
        retry_count: int = 0,
        error_code: str | None = None,
        chunk_ids: list[str] | None = None,
        tool_name: str | None = None,
        approval_decision: str | None = None,
        execution_reference: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Construct, sanitize, and log a structured workflow transition event."""
        correlation_id = get_correlation_id()
        event_payload: dict[str, Any] = {
            "service": cls.SERVICE_NAME,
            "timestamp": datetime.now(UTC).isoformat(),
            "correlation_id": correlation_id,
            "thread_id": thread_id,
            "request_id": request_id,
            "user_id_hash": anonymize_user_id(user_id),
            "node": node_name,
            "outcome": outcome,
            "retry_count": retry_count,
        }

        if duration_ms is not None:
            event_payload["duration_ms"] = round(duration_ms, 2)
        if error_code is not None:
            event_payload["error_code"] = error_code
        if chunk_ids:
            event_payload["chunk_ids"] = chunk_ids[:10]
            event_payload["chunk_count"] = len(chunk_ids)
        if tool_name is not None:
            event_payload["tool_name"] = tool_name
        if approval_decision is not None:
            event_payload["approval_decision"] = approval_decision
        if execution_reference is not None:
            event_payload["execution_reference"] = execution_reference

        if extra:
            event_payload["details"] = extra

        sanitized = recursive_redact(event_payload)
        logger.info(
            f"workflow_transition:{node_name}:{outcome}",
            extra={"workflow_event": sanitized, "correlation_id": correlation_id},
        )
        return sanitized


def init_tracing(enabled: bool = False, project_name: str = "agentic-procurement") -> None:
    """Optional LangSmith tracing initializer that gracefully degrades on failure."""
    if not enabled and os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        return

    try:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", project_name)
        logger.info("initialized LangSmith distributed tracing")
    except Exception as exc:
        logger.warning(
            "failed to initialize LangSmith tracing: %s; continuing without tracing",
            exc,
        )
