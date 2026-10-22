"""
One error envelope for every route (T-13, audit D-09).

Before T-13, 57 `HTTPException` sites returned `{"detail": "<string>"}`, a
validation error returned `{"detail": [<list>]}`, the rate limiter wrote its own
body, and an unhandled exception fell through to Starlette's plain-text 500. A
client needed four code paths to show one error.

Every 4xx and 5xx now has the `ErrorResponse` shape from `schema/models.py`:
`status`, a stable `code`, a human `message`, the `request_id` every log line
of the request carries (T-12), and `detail` — kept so a client written against
FastAPI's `detail` still works.

No status code changes here; only the body does. An unhandled exception is a
500 `internal_error` whose message says nothing about the code: the type and
traceback go to the log under the request id, never to the client.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from schema.models import ErrorResponse

from .logs import request_id

#: The stable key for each status. A route may name its own code by raising
#: `HTTPException(detail={"code": ..., "message": ...})`.
CODES: Dict[int, str] = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    413: "too_large",
    415: "unsupported_media_type",
    422: "invalid_request",
    423: "locked",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "unavailable",
    504: "timeout",
}

INTERNAL_MESSAGE = (
    "Something went wrong on our side. Nothing about your request was the cause; "
    "quote the request id if you report it."
)


def code_for(status: int) -> str:
    return CODES.get(status, "client_error" if status < 500 else "server_error")


def envelope(
    status: int,
    message: str,
    *,
    code: Optional[str] = None,
    detail: Any = None,
) -> Dict[str, Any]:
    """The body of an error response, validated against the contract."""
    return ErrorResponse(
        status=status,
        code=code or code_for(status),
        message=message,
        request_id=request_id.get(),
        detail=message if detail is None else detail,
    ).model_dump(mode="json")


def error_response(
    status: int,
    message: str,
    *,
    code: Optional[str] = None,
    detail: Any = None,
    headers: Optional[Mapping[str, str]] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=envelope(status, message, code=code, detail=detail),
        headers=dict(headers) if headers else None,
    )


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail
    code: Optional[str] = None
    if isinstance(detail, dict):
        code = detail.get("code")
        message = str(detail.get("message") or detail.get("detail") or code_for(exc.status_code))
        body_detail: Any = detail
    else:
        message = str(detail) if detail else code_for(exc.status_code).replace("_", " ")
        body_detail = None
    return error_response(
        exc.status_code, message, code=code, detail=body_detail, headers=exc.headers
    )


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    """A 422 names the fields that failed and why — and not the values sent,
    which FastAPI's default echoes back and which may be someone's evidence."""
    assert isinstance(exc, RequestValidationError)
    fields = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    first = fields[0] if fields else None
    where = ".".join(str(p) for p in first["loc"] if p != "body") if first else ""
    message = f"Invalid request: {where} — {first['msg']}" if first and where else "Invalid request."
    return error_response(422, message, detail=fields)


def install(app: FastAPI) -> None:
    """Register the handlers. The unhandled-exception case is answered in
    `logs.RequestIdMiddleware`, which is the layer that still knows the request
    id when a route raises something nobody caught."""
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)


__all__ = ["CODES", "INTERNAL_MESSAGE", "code_for", "envelope", "error_response", "install"]
