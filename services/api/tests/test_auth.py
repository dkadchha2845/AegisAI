"""
Auth & RBAC regressions — the security-critical surface, so tested in both
directions: the right credential works, and every wrong-credential / wrong-role
path is refused.

The KDF and token helpers are unit-tested directly; the login → me → admin flow
is driven through the real app with enforcement flipped on via `auth_enabled`,
which is the one seam the routes read.
"""

from __future__ import annotations

import itertools
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
        json={"email": "viewer@aegis.local", "password": "quiet-harbour-73", "role": "viewer"},
    )
    viewer = _login(enforced, "viewer@aegis.local", "quiet-harbour-73").json()["token"]
    resp = enforced.get("/api/auth/users", headers={"Authorization": f"Bearer {viewer}"})
    assert resp.status_code == 403


def test_open_mode_me_needs_no_token():
    # Default (enforcement off): /me returns the seeded admin without a token.
    client = TestClient(app)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["auth_enforced"] is False


# --- sessions: the controls have to be real in open mode too ----------------
#
# Every test below is a regression for one defect, found by running the flow
# rather than by the suite: in open mode a *refused* token fell through to the
# open-mode identity, so signing out, rotating a token and being demoted all
# left the dead token working — as the seeded **owner**, which is who the
# open-mode fallback returns. Enforced-mode tests could not see it, because the
# fallback does not exist there.


#: A password strong enough for `password_problem`, shared by the accounts the
#: fixture below provisions.
_SESSION_PW = "quiet-harbour-73"
_serial = itertools.count()


@pytest.fixture
def open_client():
    """A client in the default open (demo) mode, with a seeded database.

    The accounts are provisioned by this fixture rather than taken from the demo
    roster, and given unique addresses. The ephemeral database is one temp file
    shared by the whole session, so a fixed address collides with whatever
    another test did to that account — including the `viewer@aegis.local` that
    `test_viewer_cannot_reach_admin_route` above creates with its own password.
    """
    init_db()
    db = SessionLocal()
    try:
        auth_mod.seed_admin(db)
    finally:
        db.close()
    return TestClient(app)


def _account(role: str = "analyst") -> str:
    """Provision one account directly and return its email."""
    email = f"session{next(_serial)}.{role}@aegis.test"
    db = SessionLocal()
    try:
        auth_mod.create_user(db, email, _SESSION_PW, role=role)
    finally:
        db.close()
    return email


def _open_login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": _SESSION_PW})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_open_mode_still_needs_no_credential_at_all(open_client):
    """The demo's whole premise. A request with no Authorization header is the
    seeded owner, exactly as before."""
    r = open_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["auth_enforced"] is False
    assert r.json()["user"]["role"] == "owner"


def test_open_mode_logout_ends_the_session(open_client):
    token = _open_login(open_client, _account("analyst"))
    hdr = {"Authorization": f"Bearer {token}"}
    assert open_client.get("/api/auth/me", headers=hdr).json()["user"]["role"] == "analyst"
    assert open_client.post("/api/auth/logout", headers=hdr).status_code == 200
    assert open_client.get("/api/auth/me", headers=hdr).status_code == 401


def test_a_refused_token_is_never_upgraded_to_the_open_mode_owner(open_client):
    """The escalation this fixed, stated directly.

    A dead token must be refused, not silently promoted to the highest-privilege
    account in the system.
    """
    token = _open_login(open_client, _account("analyst"))
    hdr = {"Authorization": f"Bearer {token}"}
    open_client.post("/api/auth/logout", headers=hdr)

    for path in ("/api/auth/me", "/api/auth/users", "/api/orgs", "/api/audit"):
        r = open_client.get(path, headers=hdr)
        assert r.status_code == 401, f"{path} answered {r.status_code} to a revoked token"


def test_open_mode_rejects_a_garbage_token_rather_than_ignoring_it(open_client):
    r = open_client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_open_mode_refresh_retires_the_old_token(open_client):
    old = _open_login(open_client, _account("viewer"))
    new = open_client.post(
        "/api/auth/refresh", headers={"Authorization": f"Bearer {old}"}
    ).json()["token"]
    assert new != old
    assert open_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new}"}
    ).status_code == 200
    assert open_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old}"}
    ).status_code == 401


def test_open_mode_sign_out_everywhere_keeps_the_calling_session(open_client):
    email = _account("citizen")
    first = _open_login(open_client, email)
    second = _open_login(open_client, email)
    revoked = open_client.delete(
        "/api/auth/sessions", headers={"Authorization": f"Bearer {second}"}
    ).json()["revoked"]
    assert revoked >= 1
    assert open_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {second}"}
    ).status_code == 200
    assert open_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {first}"}
    ).status_code == 401
