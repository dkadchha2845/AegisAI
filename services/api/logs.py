"""
Structured logs with a request and a case ID on every line (T-12, audit D-08).

**Why it exists.** Before T-12 the service wrote sixteen bare `print()` lines
with no time, no level and nothing tying one to the request or investigation
that caused it. Following a case from the route, through the graph and each
agent, to the worker meant guessing from timestamps that were not there.

**What it does.** `configure()` installs one JSON-lines handler on the `aegis`
logger. Two context variables, `request_id` and `case_id`, are stamped onto
every record by a filter, so a line need not pass them. Context variables
follow an `await`, an `asyncio.create_task` (which copies the context it was
created in) and `asyncio.to_thread`, so an investigation started by a request
logs under that request's ID and its own case ID wherever it runs.

**What it must never log.** Evidence text, a session or reset token, a
password, or a person's email address. Lines carry identifiers the system
minted (`request_id`, `case_id`, agent names) and measurements. The request
line records the route *path* and never the query string, because a live
session's `?token=` travels there.

Named `logs` rather than `logging` so that nothing in this package can shadow
the standard library module it is built on.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
case_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("case_id", default=None)

ROOT = "aegis"

#: Attributes every `LogRecord` has. Anything else on a record came from
#: `extra=` and is emitted as a field.
_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id", "case_id"}

#: A client-supplied `X-Request-ID` is accepted only in this shape, so a
#: header cannot inject newlines, JSON or a megabyte into every log line.
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        record.case_id = case_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, logger, message, the two IDs,
    and any `extra=` fields."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "case_id": getattr(record, "case_id", None),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith("_"):
                out[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            out["exc_type"] = record.exc_info[0].__name__
            # Bounded: a traceback names code, not data, but an exception's
            # message is whatever its raiser put in it.
            out["traceback"] = self.formatException(record.exc_info)[-4000:]
        return json.dumps(out, default=str, ensure_ascii=False)


_configured = False


def configure(level: Optional[str] = None) -> None:
    """Install the handler once. Idempotent, so every entry point may call it.

    `level` is `settings.log_level` (`AEGIS_LOG_LEVEL`, default INFO) at both
    entry points. The logger does not propagate to the root, so a host that
    configures its own root logging does not print every line twice.
    """
    global _configured
    logger = logging.getLogger(ROOT)
    logger.setLevel((level or "INFO").upper())
    if _configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_ContextFilter())
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """A child of the `aegis` logger. Records reach the handler with the
    context stamped on, wherever the logger was created."""
    logger = logging.getLogger(f"{ROOT}.{name}")
    if not any(isinstance(f, _ContextFilter) for f in logger.filters):
        logger.addFilter(_ContextFilter())
    return logger


def new_request_id(supplied: Optional[str] = None) -> str:
    """The caller's ID if it is well formed, else a fresh one."""
    if supplied and _VALID_ID.match(supplied):
        return supplied
    return uuid.uuid4().hex


@contextlib.contextmanager
def bind(*, request: Optional[str] = None, case: Optional[str] = None) -> Iterator[None]:
    """Set the IDs for everything logged inside the block, then restore them."""
    tokens = []
    if request is not None:
        tokens.append((request_id, request_id.set(request)))
    if case is not None:
        tokens.append((case_id, case_id.set(case)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def describe_error(exc: BaseException, limit: int = 200) -> str:
    """An exception for a log line: its type and a bounded message. Bounded
    because some libraries put the request they were given in the message."""
    text = str(exc).replace("\n", " ")
    return f"{type(exc).__name__}: {text[:limit]}"


class RequestIdMiddleware:
    """Give every request an ID, return it, and log one line when it ends.

    Pure ASGI rather than `BaseHTTPMiddleware`: the ID is set before any other
    layer runs and seen by all of them, a WebSocket gets one too, and a 429
    from the rate limiter or a 500 still carries the header. The line records
    method, route path, status and duration — never the query string, the
    body, or a header value.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self.log = get_logger("http")

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        supplied = None
        for name, value in scope.get("headers") or []:
            if name == b"x-request-id":
                supplied = value.decode("latin-1")
                break
        rid = new_request_id(supplied)
        status = {"code": 500, "started": False}

        async def send_with_id(message: Any) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                status["started"] = True
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", rid.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        started = time.perf_counter()
        token = request_id.set(rid)
        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            # Nothing caught it. Answer here, where the request id is still
            # set, in the same envelope as every other error (T-13): the type
            # and traceback go to the log under this id, and none of it goes
            # to the client. A WebSocket, or a response already half-sent, can
            # only be closed, so those re-raise.
            self.log.error("unhandled exception", exc_info=exc,
                           extra={"error": describe_error(exc)})
            if scope["type"] != "http" or status["started"]:
                raise
            from .errors import INTERNAL_MESSAGE, error_response

            await error_response(500, INTERNAL_MESSAGE)(scope, receive, send_with_id)
        finally:
            route = scope.get("route")
            self.log.info(
                "request",
                extra={
                    "method": scope.get("method", "WS"),
                    "path": getattr(route, "path", None) or scope.get("path"),
                    "status": status["code"],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id.reset(token)


__all__ = [
    "JsonFormatter",
    "RequestIdMiddleware",
    "bind",
    "case_id",
    "configure",
    "describe_error",
    "get_logger",
    "new_request_id",
    "request_id",
]
