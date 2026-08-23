"""
Auth & RBAC regressions — the security-critical surface, so tested in both
directions: the right credential works, and every wrong-credential / wrong-role
path is refused.

The KDF and token helpers are unit-tested directly; the login → me → admin flow
is driven through the real app with enforcement flipped on via `auth_enabled`,
which is the one seam the routes read.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from services.api import auth as auth_mod
from services.api.auth import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from services.api.db import SessionLocal, init_db
from services.api.main import app
from services.api.models_db import User

# --- password hashing -------------------------------------------------------

def test_password_hash_round_trips_and_rejects_wrong():
    stored = hash_password("correct horse battery staple")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong password", stored)


def test_password_hash_is_salted():
    # Same password, two hashes -> different salts, so identical stored strings
    # never leak that two users share a password.
    assert hash_password("same") != hash_password("same")


def test_verify_is_safe_on_garbage():
    assert not verify_password("x", "not-a-valid-hash-string")


# --- tokens -----------------------------------------------------------------

def _fake_user(uid=1, email="a@b.com", role="admin"):
    u = User(email=email, password_hash="x", role=role)
    u.id = uid
    return u


def test_token_round_trips():
    claims = decode_token(create_token(_fake_user(uid=7, role="analyst")))
    assert claims is not None
    assert claims["uid"] == 7 and claims["role"] == "analyst"


def test_tampered_token_is_rejected():
    token = create_token(_fake_user())
    head, payload, sig = token.split(".")
    forged = f"{head}.{payload}.{'A' * len(sig)}"
    assert decode_token(forged) is None
    assert decode_token("garbage") is None


def test_expired_token_is_rejected(monkeypatch):
    token = create_token(_fake_user())
    # Advance the clock the auth module reads to well past the token's expiry.
    future = time.time() + auth_mod.settings.token_ttl_s + 10
    monkeypatch.setattr(auth_mod.time, "time", lambda: future)
    assert decode_token(token) is None


# --- the login / RBAC flow --------------------------------------------------

@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setattr(auth_mod, "auth_enabled", lambda: True)
    init_db()
    # Ensure the seeded admin exists.
    db = SessionLocal()
    try:
        auth_mod.seed_admin(db)
    finally:
        db.close()
    return TestClient(app)


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_success_and_me(enforced):
    r = _login(enforced, "admin@aegis.local", "changeme")
    assert r.status_code == 200
    token = r.json()["token"]
    me = enforced.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    # The seeded account is the platform owner (superadmin), which outranks admin
    # so every admin-gated route still resolves for it.
    assert body["user"]["role"] == "owner"
    # It belongs to the default tenant, and /me now carries that org.
    assert body["org"] is not None
    assert body["org"]["slug"] == "aegis"


def test_login_wrong_password_is_401(enforced):
    assert _login(enforced, "admin@aegis.local", "nope").status_code == 401


def test_login_unknown_email_is_401(enforced):
    # Same status as a wrong password — no account-existence oracle.
    assert _login(enforced, "ghost@nowhere.com", "whatever").status_code == 401


def test_protected_route_requires_token(enforced):
    assert enforced.get("/api/auth/users").status_code == 401


def test_viewer_cannot_reach_admin_route(enforced):
    admin = _login(enforced, "admin@aegis.local", "changeme").json()["token"]
    # Admin creates a viewer.
    enforced.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {admin}"},
        json={"email": "viewer@aegis.local", "password": "viewerpass1", "role": "viewer"},
    )
    viewer = _login(enforced, "viewer@aegis.local", "viewerpass1").json()["token"]
    resp = enforced.get("/api/auth/users", headers={"Authorization": f"Bearer {viewer}"})
    assert resp.status_code == 403


def test_open_mode_me_needs_no_token():
    # Default (enforcement off): /me returns the seeded admin without a token.
    client = TestClient(app)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["auth_enforced"] is False
