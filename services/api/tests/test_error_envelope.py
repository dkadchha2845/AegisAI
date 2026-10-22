"""
Every error has one shape (T-13, audit D-09).

Before T-13 a client needed four code paths: `{"detail": str}` from
`HTTPException`, `{"detail": [...]}` from validation, the rate limiter's own
body, and Starlette's plain-text 500. Each test here produces one class of
error and asserts the same envelope, with the request id the response header
carries.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from schema.models import ErrorResponse
from services.api import auth as auth_mod
from services.api.db import SessionLocal, init_db
from services.api.errors import INTERNAL_MESSAGE
from services.api.errors import install as install_errors
from services.api.logs import RequestIdMiddleware
from services.api.main import app
from services.api.security import RateLimitMiddleware

FIELDS = set(ErrorResponse.model_fields)


def assert_envelope(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == FIELDS, body
    ErrorResponse.model_validate(body)
    assert body["status"] == status and body["code"] == code
    assert body["message"]
    assert body["request_id"] == response.headers["x-request-id"]
    return body


@pytest.fixture
def client() -> Iterator[TestClient]:
    init_db()
    with TestClient(app) as c:
        yield c


def test_a_validation_error(client: TestClient) -> None:
    body = assert_envelope(client.post("/api/analyze/text", json={}), 422, "invalid_request")
    assert body["detail"][0]["loc"][-1] == "text"
    assert "text" in body["message"]


def test_a_validation_error_does_not_echo_what_was_sent(client: TestClient) -> None:
    """FastAPI's default 422 copies the submitted value back. A value here may
    be someone's evidence, and a 422 body is the kind of thing that gets pasted
    into a bug report."""
    r = client.post("/api/analyze/text", json={"text": 12345678901234567890, "explain": "SECRET-EVIDENCE"})
    assert_envelope(r, 422, "invalid_request")
    assert "SECRET-EVIDENCE" not in r.text


def test_a_case_that_does_not_exist(client: TestClient) -> None:
    body = assert_envelope(client.get("/api/investigations/AEG-DOES-NOT-EXIST"), 404, "not_found")
    assert body["detail"] == body["message"]  # the field a FastAPI client already reads


def test_a_route_that_does_not_exist(client: TestClient) -> None:
    assert_envelope(client.get("/api/no-such-route"), 404, "not_found")


def test_a_method_that_is_not_allowed(client: TestClient) -> None:
    assert_envelope(client.delete("/api/health"), 405, "method_not_allowed")


def test_an_unsupported_upload(client: TestClient) -> None:
    r = client.post(
        "/api/analyze/image", files={"file": ("note.txt", b"just text", "text/plain")}
    )
    assert_envelope(r, 415, "unsupported_media_type")


def test_unauthenticated_and_forbidden(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(auth_mod, "auth_enabled", lambda: True)
    db = SessionLocal()
    try:
        auth_mod.seed_admin(db)
    finally:
        db.close()
    assert_envelope(client.get("/api/audit"), 401, "unauthenticated")

    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "envelope.citizen@example.org",
            "password": "Correct-Horse-91",
            "confirm_password": "Correct-Horse-91",
            "full_name": "Envelope Citizen",
            "accept_terms": True,
        },
    )
    assert signup.status_code in (200, 201), signup.text
    token = signup.json()["token"]
    r = client.get("/api/audit", headers={"Authorization": f"Bearer {token}"})
    assert_envelope(r, 403, "forbidden")


# --- built on a small app, so the error can be produced on demand -------------


def _small_app(*, rate_limited: bool = False) -> FastAPI:
    small = FastAPI()

    @small.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("internal detail /srv/aegisai/secret.py line 42")

    @small.get("/api/ok")
    def ok() -> dict:
        return {"ok": True}

    install_errors(small)
    if rate_limited:
        small.add_middleware(RateLimitMiddleware, enabled=True)
    small.add_middleware(RequestIdMiddleware)
    return small


def test_an_unhandled_exception_is_a_500_envelope_with_no_stack_trace() -> None:
    with TestClient(_small_app()) as c:
        r = c.get("/api/boom")
    body = assert_envelope(r, 500, "internal_error")
    assert body["message"] == INTERNAL_MESSAGE
    for leaked in ("RuntimeError", "secret.py", "Traceback"):
        assert leaked not in r.text


def test_the_rate_limiter_uses_the_envelope() -> None:
    with TestClient(_small_app(rate_limited=True)) as c:
        responses = [c.get("/api/ok") for _ in range(260)]
    limited = next(r for r in responses if r.status_code == 429)
    assert_envelope(limited, 429, "rate_limited")
    assert limited.headers["retry-after"]
