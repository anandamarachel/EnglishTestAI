"""Shared error envelope: {code, message, request_id, retryable, details}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_id import get_request_id

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Raise from services/routers to return a contract error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or []
        self.headers = headers
        self.extra = extra or {}


def unauthorized(message: str = "Authentication required.", code: str = "UNAUTHORIZED"):
    return ApiError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def validation_error(field: str, message: str) -> ApiError:
    return ApiError(
        422,
        "VALIDATION_ERROR",
        "Request validation failed.",
        details=[{"field": field, "message": message}],
    )


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body = {
        "code": code,
        "message": message,
        "request_id": get_request_id(request),
        "retryable": retryable,
        "details": details or [],
        **(extra or {}),
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


_HTTP_CODES = {
    400: ("BAD_REQUEST", "Malformed request."),
    401: ("UNAUTHORIZED", "Authentication required."),
    403: ("FORBIDDEN", "Operation not permitted."),
    404: ("NOT_FOUND", "Resource not found."),
    405: ("METHOD_NOT_ALLOWED", "Method not allowed."),
    413: ("CAPACITY_EXCEEDED", "Request exceeds processing capacity."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type."),
    429: ("RATE_LIMITED", "Too many requests."),
}


def _field_name(location: tuple[Any, ...]) -> str:
    # ("body", "email") -> "email"; never include the submitted value.
    parts = [str(part) for part in location if part not in ("body", "query", "path", "header")]
    return ".".join(parts) or "body"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(
            request,
            exc.status_code,
            exc.code,
            exc.message,
            retryable=exc.retryable,
            details=exc.details,
            headers=exc.headers,
            extra=exc.extra,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        if any(error.get("type") == "json_invalid" for error in errors):
            return error_response(request, 400, "BAD_REQUEST", "Malformed JSON body.")
        # Only field names and generic messages: Pydantic's "input"/"ctx" may hold secrets.
        details = [
            {"field": _field_name(tuple(error.get("loc", ()))), "message": error.get("msg", "")}
            for error in errors
        ]
        return error_response(
            request, 422, "VALIDATION_ERROR", "Request validation failed.", details=details
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_CODES.get(exc.status_code, ("HTTP_ERROR", "Request failed."))
        return error_response(
            request, exc.status_code, code, message, headers=getattr(exc, "headers", None)
        )

    @app.exception_handler(OperationalError)
    async def handle_db_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
        # Driver messages can contain connection details; log the type only.
        logger.warning("Database unavailable: %s", type(exc.orig).__name__)
        return error_response(
            request,
            503,
            "SERVICE_UNAVAILABLE",
            "Service is temporarily unavailable.",
            retryable=True,
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(DBAPIError)
    async def handle_db_error(request: Request, exc: DBAPIError) -> JSONResponse:
        logger.error("Unhandled database error: %s", type(exc.orig).__name__)
        return error_response(request, 500, "INTERNAL_ERROR", "Unexpected server error.")

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error (request_id=%s)", get_request_id(request))
        return error_response(request, 500, "INTERNAL_ERROR", "Unexpected server error.")
