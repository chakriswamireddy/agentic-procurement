import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_correlation_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    code: str = "error"
    status_code: int = 500
    message: str = "unexpected error"
    details: dict[str, Any] = {}

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or type(self).message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    message = "resource not found"


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422
    message = "invalid request"


class ConflictError(AppError):
    code = "conflict"
    status_code = 409
    message = "resource conflict"


class WorkflowError(AppError):
    code = "workflow_error"
    status_code = 500
    message = "workflow execution failed"


class DependencyUnavailableError(AppError):
    code = "dependency_unavailable"
    status_code = 503
    message = "dependency unavailable"


class IngestionFailedError(AppError):
    code = "ingestion_failed"
    status_code = 500
    message = "document ingestion failed"


class UnauthorizedError(AppError):
    code = "unauthorized"
    status_code = 401
    message = "unauthorized"


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = 403
    message = "forbidden"


def _envelope(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "correlation_id": get_correlation_id(),
        }
    }


def _http_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        503: "dependency_unavailable",
    }.get(status_code, "http_error")


def _sanitize_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    sanitized = []
    for error in exc.errors():
        sanitized.append(
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return sanitized


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code=exc.code, message=exc.message, details=exc.details),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_envelope(
            code="validation_error",
            message="request validation failed",
            details={"errors": _sanitize_validation_errors(exc)},
        ),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(
            code=_http_code(exc.status_code),
            message=detail,
        ),
        headers=getattr(exc, "headers", None),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled exception",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
        },
    )
    return JSONResponse(
        status_code=500,
        content=_envelope(code="internal_error", message="internal server error"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
