"""
Security middleware — rate limiting, login backoff, and hardening headers.

Two ASGI middlewares and one login guard, all dependency-free and in-process, in
keeping with the rest of the service: nothing here needs Redis or a WAF to run
the demo, and each degrades to "allow" rather than failing a request if its own
bookkeeping is somehow inconsistent.

  * `SecurityHeadersMiddleware` sets the headers a security product is expected
    to set on every response — CSP, X-Content-Type-Options, X-Frame-Options,
    Referrer-Policy, and a conservative Permissions-Policy. The CSP is strict
    (`default-src 'none'`) because the API serves only JSON and PDFs; the SPA is
    served by Vite/its own host, not from here.

  * `RateLimitMiddleware` is a token-bucket limiter keyed on client IP + a coarse
    route class, so a burst of citizen `verify` calls or auth attempts cannot be
    used to hammer the analyzer or brute-force a password. Limits are generous
    enough that no human demo hits them and tight enough that a script does.

  * `record_login_attempt` / `login_locked` add per-identifier backoff on top of
    the uniform-401 login: after several failures for one email+IP the endpoint
    responds 429 for a cooling-off window. This is the CWE-307 control the audit
    flagged as missing.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# --- security headers -------------------------------------------------------

_CSP = (
    "default-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for k, v in _HEADERS.items():
            response.headers.setdefault(k, v)
        return response


# --- rate limiting ----------------------------------------------------------

# (requests, per_seconds) by route class. Auth is tightest (brute force),
# analysis/verify next (compute), everything else generous.
_LIMITS: Dict[str, Tuple[int, float]] = {
    "auth": (10, 60.0),        # 10 login attempts / minute / IP
    "analyze": (40, 60.0),     # 40 analyses / minute / IP
    "shield": (40, 60.0),      # citizen verify/preserve
    "write": (30, 60.0),       # other POST/DELETE
    "read": (240, 60.0),       # GETs — dashboards poll, so generous
}


def _route_class(request: Request) -> str:
    path = request.url.path
    method = request.method
    if path.startswith("/api/auth/login"):
        return "auth"
    if path.startswith("/api/analyze"):
        return "analyze"
    if path.startswith("/api/shield"):
        return "shield"
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return "write"
    return "read"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window-ish sliding limiter. In-process, per (ip, route-class)."""

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled:
            return await call_next(request)
        # Never rate-limit CORS preflight — the browser needs it to even reach
        # the real request, and it carries no credentials.
        if request.method == "OPTIONS":
            return await call_next(request)

        cls = _route_class(request)
        limit, window = _LIMITS.get(cls, _LIMITS["read"])
        ip = request.client.host if request.client else "unknown"
        key = (ip, cls)
        now = time.monotonic()

        with self._lock:
            q = self._hits[key]
            cutoff = now - window
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                retry = max(1, int(q[0] + window - now))
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Rate limit exceeded. Retry in {retry}s."},
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)

        return await call_next(request)


# --- login backoff ----------------------------------------------------------

_LOGIN_FAILS: Dict[str, Deque[float]] = defaultdict(deque)
_LOGIN_LOCK = threading.Lock()
_MAX_FAILS = 5
_FAIL_WINDOW = 300.0   # 5 failed attempts within 5 minutes …
_LOCK_FOR = 300.0      # … locks that identifier for 5 minutes


def _login_key(email: str, ip: str) -> str:
    return f"{email.lower().strip()}|{ip}"


def login_locked(email: str, ip: str) -> float:
    """Seconds remaining on a lock for this email+IP, or 0 if not locked."""
    key = _login_key(email, ip)
    now = time.monotonic()
    with _LOGIN_LOCK:
        q = _LOGIN_FAILS[key]
        while q and q[0] < now - _FAIL_WINDOW:
            q.popleft()
        if len(q) >= _MAX_FAILS:
            unlock_at = q[-1] + _LOCK_FOR
            return max(0.0, unlock_at - now)
    return 0.0


def record_login_attempt(email: str, ip: str, *, success: bool) -> None:
    """Record a login outcome; a success clears the failure history."""
    key = _login_key(email, ip)
    now = time.monotonic()
    with _LOGIN_LOCK:
        if success:
            _LOGIN_FAILS.pop(key, None)
        else:
            _LOGIN_FAILS[key].append(now)
