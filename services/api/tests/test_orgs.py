"""
Multi-tenant isolation tests.

The property that matters for a security product: an org admin sees only their own
org's users, cases, and audit — never another tenant's — while the platform owner
sees across all of them. This is the IDOR / broken-object-level-auth control the
audit flagged, so it is tested directly.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def enforced(monkeypatch):
    """A client with auth enforced and rate limiting off, fresh DB per test."""
    monkeypatch.setenv("AEGIS_AUTH", "1")
    monkeypatch.setenv("AEGIS_RATELIMIT", "0")
    # Re-import settings-bound modules so the env flips take effect.
    import importlib

    from services.api import config as config_mod
    importlib.reload(config_mod)
    import services.api.auth as auth_mod
    importlib.reload(auth_mod)
    import services.api.security as sec_mod
    importlib.reload(sec_mod)
    import services.api.main as main_mod
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as client:
        yield client


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["token"] if r.status_code == 200 else None


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_create_org_and_scope_users(enforced):
    owner = _login(enforced, "admin@aegis.local", "changeme")
    assert owner

    # Owner creates a second org.
    r = enforced.post("/api/orgs", json={"name": "Delhi Cyber Cell"}, headers=_auth(owner))
    assert r.status_code == 201
    org2 = r.json()["organization"]

    # Owner adds an admin into that org.
    r = enforced.post(
        "/api/auth/users",
        json={"email": "delhi.admin@x.gov.in", "password": "password123",
              "role": "admin", "org_id": org2["id"]},
        headers=_auth(owner),
    )
    assert r.status_code == 201
    assert r.json()["user"]["org_id"] == org2["id"]

    # The org admin logs in and sees ONLY their own org's users.
    delhi = _login(enforced, "delhi.admin@x.gov.in", "password123")
    r = enforced.get("/api/auth/users", headers=_auth(delhi))
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()["users"]}
    assert emails == {"delhi.admin@x.gov.in"}
    assert "admin@aegis.local" not in emails

    # The owner sees everyone across all orgs.
    r = enforced.get("/api/auth/users", headers=_auth(owner))
    all_emails = {u["email"] for u in r.json()["users"]}
    assert {"admin@aegis.local", "delhi.admin@x.gov.in"} <= all_emails


def test_org_admin_cannot_create_owner(enforced):
    owner = _login(enforced, "admin@aegis.local", "changeme")
    enforced.post("/api/orgs", json={"name": "Mumbai Cell"}, headers=_auth(owner))
    # Make an org admin.
    enforced.post(
        "/api/auth/users",
        json={"email": "mum.admin@x.gov.in", "password": "password123", "role": "admin"},
        headers=_auth(owner),
    )
    admin = _login(enforced, "mum.admin@x.gov.in", "password123")
    # That admin trying to mint an owner is forbidden.
    r = enforced.post(
        "/api/auth/users",
        json={"email": "sneaky@x.gov.in", "password": "password123", "role": "owner"},
        headers=_auth(admin),
    )
    assert r.status_code == 403


def test_non_owner_cannot_list_orgs(enforced):
    owner = _login(enforced, "admin@aegis.local", "changeme")
    enforced.post(
        "/api/auth/users",
        json={"email": "analyst@x.gov.in", "password": "password123", "role": "analyst"},
        headers=_auth(owner),
    )
    analyst = _login(enforced, "analyst@x.gov.in", "password123")
    assert enforced.get("/api/orgs", headers=_auth(analyst)).status_code == 403
    # …but any signed-in user can read which org they are in.
    assert enforced.get("/api/orgs/current", headers=_auth(analyst)).status_code == 200
