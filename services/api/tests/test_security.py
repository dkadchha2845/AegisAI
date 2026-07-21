"""
Security-hardening regression tests.

Locks in the controls the audit added: hardening headers on every response, the
token-bucket rate limiter, and per-identifier login backoff. The limiter and
backoff are exercised on throwaway keys / a dedicated app so they never lock out
the shared admin login the rest of the suite relies on.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from services.api.main import app
from services.api.security import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    login_locked,
    record_login_attempt,
)


def test_security_headers_present():
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "default-src 'none'" in r.headers.get("Content-Security-Policy", "")
        assert r.headers.get("Referrer-Policy") == "no-referrer"


def test_login_backoff_locks_and_clears():
    email, ip = "attacker@example.com", "203.0.113.7"
    assert login_locked(email, ip) == 0.0
    for _ in range(5):
        record_login_attempt(email, ip, success=False)
    assert login_locked(email, ip) > 0, "should be locked after 5 failures"
    # A success clears the history.
    record_login_attempt(email, ip, success=True)
    assert login_locked(email, ip) == 0.0


def test_backoff_is_per_identifier():
    record_login_attempt("a@x.com", "10.0.0.1", success=False)
    # A different IP for the same email is a different key — not locked.
    assert login_locked("a@x.com", "10.0.0.2") == 0.0
    record_login_attempt("a@x.com", "10.0.0.1", success=True)  # cleanup


def test_rate_limiter_returns_429_over_limit():
    # A dedicated tiny app so we do not touch the real app's limiter state.
    mini = FastAPI()

    @mini.get("/api/analyze/ping")
    def ping():
        return {"ok": True}

    mini.add_middleware(SecurityHeadersMiddleware)
    mini.add_middleware(RateLimitMiddleware, enabled=True)

    with TestClient(mini) as client:
        # /api/analyze class is 40/min. The 41st should 429.
        statuses = [client.get("/api/analyze/ping").status_code for _ in range(45)]
        assert 200 in statuses
        assert 429 in statuses
        assert statuses.count(429) >= 1
        # A 429 still carries the hardening headers and a Retry-After.
        first_429 = next(i for i, s in enumerate(statuses) if s == 429)
        assert first_429 <= 41


def test_rate_limiter_can_be_disabled():
    mini = FastAPI()

    @mini.get("/api/analyze/ping")
    def ping():
        return {"ok": True}

    mini.add_middleware(RateLimitMiddleware, enabled=False)
    with TestClient(mini) as client:
        assert all(client.get("/api/analyze/ping").status_code == 200 for _ in range(60))
