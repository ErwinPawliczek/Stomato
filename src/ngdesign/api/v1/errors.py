"""The v1 error envelope: every 4xx/5xx under ``/api/v1`` is

    {"error": {"code": "<stable code>", "message": "<how to fix>", "details": {...}}}

Legacy routes keep FastAPI's ``{"detail": ...}`` byte-for-byte; the app's
exception handlers call :func:`error_response`, which picks the shape by path.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PREFIX = "/api/v1"

#: Default codes for bare HTTP statuses (HTTPException raised without a code).
STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "invalid",
    500: "internal_error",
    501: "not_implemented",
}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    """Every v1 error response."""

    error: ErrorBody


def is_v1(request: Request) -> bool:
    return request.url.path == PREFIX or request.url.path.startswith(PREFIX + "/")


def envelope(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def error_response(
    request: Request,
    status: int,
    message: str,
    *,
    code: str | None = None,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """The v1 envelope under /api/v1, else the legacy ``{"detail": message}``."""
    if is_v1(request):
        response = envelope(status, code or STATUS_CODES.get(status, "error"), message, details)
    else:
        response = JSONResponse(status_code=status, content={"detail": message})
    if headers:
        response.headers.update(headers)
    return response


#: OpenAPI ``responses`` entry documenting the envelope on every v1 route.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorEnvelope, "description": desc}
    for status, desc in (
        (404, "Unknown project, unit, stream, address, ..."),
        (409, "Conflict: duplicate, stale version, nothing to undo"),
        (422, "Invalid input (code names the rule)"),
    )
}
