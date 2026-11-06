import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import unhandled_exception_handler
from app.core.logging import correlation_id_var

logger = logging.getLogger("app.request")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def sanitize_request_id(value: str | None) -> str | None:
    if value is not None and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = sanitize_request_id(request.headers.get("X-Request-ID"))
        if request_id is None:
            request_id = str(uuid.uuid4())

        token = correlation_id_var.set(request_id)
        started = time.perf_counter()

        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                response = await unhandled_exception_handler(request, exc)

            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            correlation_id_var.reset(token)
