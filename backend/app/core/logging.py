import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import redact_value

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_EXTRA_FIELDS = (
    "correlation_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
)


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


def _redact_record(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }

    for field in _EXTRA_FIELDS:
        value = getattr(record, field, None)
        if value is not None:
            payload[field] = value

    correlation_id = get_correlation_id()
    if correlation_id is not None:
        payload.setdefault("correlation_id", correlation_id)

    return {key: redact_value(key, value) for key, value in payload.items()}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = _redact_record(record)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = _redact_record(record)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        head = (
            f"{payload['timestamp']} {payload['level']} "
            f"{payload['logger']} {payload['message']}"
        )
        tail = " ".join(
            f"{key}={payload[key]}"
            for key in (*_EXTRA_FIELDS, "exception")
            if key in payload
        )
        return f"{head} {tail}".rstrip()


def setup_logging(level: str = "INFO", app_env: str = "development") -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    if app_env == "development":
        handler.setFormatter(HumanFormatter())
    else:
        handler.setFormatter(JsonFormatter())

    root.addHandler(handler)
    root.setLevel(level.upper())

    logging.getLogger("uvicorn.access").disabled = True
