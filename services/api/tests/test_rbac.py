"""
The security audit, run as tests — §38 and §39 of the specification, driven
through the real application with enforcement on.

Every case below is one line of that audit. The negative cases matter more than
the positive ones and there are deliberately more of them: a role that cannot
reach its own dashboard is a bug someone reports in the first minute, and a role
that can reach someone else's case is a bug nobody reports at all.

Enforcement is switched on the way `test_orgs.py` does it — flip the env, reload
the settings-bound modules, and **reload them back afterwards**, so this file
cannot leave the rest of the session in enforced mode.
"""

from __future__ import annotations

import importlib
import itertools

import pytest
from fastapi.testclient import TestClient

from services.api.permissions import ROLES

#: Strong enough for `password_problem`, and the same everywhere so a failure
#: is never "which password did that fixture use".
PASSWORD = "quiet-harbour-73"

#: The roles this file provisions an account for. The owner is the seeded one.
UNDER_TEST = ("citizen", "viewer", "researcher", "analyst", "police", "admin")

#: Emails are unique per test, not per file. The ephemeral database is a
#: per-process temp file that every test in the session shares, so a fixed
#: address would be a 409 on the second test — and worse, the tests that demote,
#: disable or re-password an account would hand the next test a broken one.
_serial = itertools.count()


def _emails() -> dict[str, str]:
    n = next(_serial)
    return {role: f"rbac{n}.{role}@aegis.test" for role in UNDER_TEST}


def _reload_stack():
    from services.api import config as config_mod

    importlib.reload(config_mod)
    import services.api.auth as auth_mod

    importlib.reload(auth_mod)
    import services.api.security as sec_mod

    importlib.reload(sec_mod)
    import services.api.main as main_mod

    importlib.reload(main_mod)
    return main_mod


@pytest.fixture()
def app_client(monkeypatch):
    """An enforced server, a fresh database, and one signed-in account per role.

    Rate limiting is off: this file makes far more than ten credential requests
    a minute on purpose, and the limiter's own behaviour is `test_security.py`'s
    subject rather than this one's.
    """
    monkeypatch.setenv("AEGIS_AUTH", "1")
    monkeypatch.setenv("AEGIS_RATELIMIT", "0")
    monkeypatch.setenv("AEGIS_SIGNUP", "1")
    monkeypatch.setenv("AEGIS_DEV_PASSWORD_RESET", "0")
    main_mod = _reload_stack()
    try:
        with TestClient(main_mod.app) as client:
            yield client
    finally:
        for name in ("AEGIS_AUTH", "AEGIS_RATELIMIT", "AEGIS_SIGNUP", "AEGIS_DEV_PASSWORD_RESET"):
            monkeypatch.delenv(name, raising=False)
        _reload_stack()


def _login(client, email, password=PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json().get("token") if r.status_code == 200 else None


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


class Roles:
    """One signed-in account per role, for one test.

    `tokens[role]` is a bearer token and `emails[role]` is the address behind
    it. Both are needed: half the audit is about what a token can reach, and the
    other half is about what happens to the account it belongs to.
    """

    def __init__(self, tokens: dict[str, str], emails: dict[str, str]) -> None:
        self.tokens = tokens
        self.emails = emails

    def __getitem__(self, role: str) -> str:
        return self.tokens[role]

    def email(self, role: str) -> str:
        return self.emails[role]


@pytest.fixture()
def roles(app_client):
    """An account per role, provisioned through the API by the owner — so the
    provisioning path is itself exercised on every test that uses this."""
    owner = _login(app_client, "admin@aegis.local", "changeme")
    assert owner, "the seeded owner must be able to sign in"
    emails = _emails()
    tokens = {"owner": owner}
    for role, email in emails.items():
        r = app_client.post(
            "/api/auth/users",
            json={"email": email, "password": PASSWORD, "role": role,
                  "full_name": f"{role.title()} Under Test"},
            headers=_hdr(owner),
        )
        assert r.status_code == 201, (role, r.status_code, r.text)
        token = _login(app_client, email)
        assert token, f"{role} must be able to sign in"
        tokens[role] = token
    return Roles(tokens, emails)


# ---------------------------------------------------------------------------
# §39 — unauthenticated access
# ---------------------------------------------------------------------------

PROTECTED = [
    ("GET", "/api/auth/users"),
    ("GET", "/api/auth/me"),
    ("GET", "/api/reports"),
    ("GET", "/api/audit"),
    ("GET", "/api/orgs"),
    ("GET", "/api/intel/clusters"),
    ("GET", "/api/investigations"),
    ("GET", "/api/research/overview"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_no_protected_route_answers_without_a_token(app_client, method, path):
    """'direct API request without authentication' — the whole list, not a
    sample, because the one route that forgot its dependency is exactly the one
    a sample misses."""
    assert app_client.request(method, path).status_code == 401


def test_a_forged_token_is_refused(app_client, roles):
    """'manipulated role in frontend'. The role in a token is a claim; what a
    user may do is read from the row. Re-signing is impossible without the key,
    and editing the payload breaks the signature."""
    token = roles["citizen"]
    head, payload, sig = token.split(".")
    forged = f"{head}.{payload}.{'A' * len(sig)}"
    assert app_client.get("/api/auth/me", headers=_hdr(forged)).status_code == 401


def test_a_token_for_a_demoted_user_carries_no_stale_privilege(app_client, roles):
    """The role is read from the database on every request, so an admin who
    demotes someone does not have to wait out their token's TTL."""
    owner = roles["owner"]
    users = app_client.get("/api/auth/users", headers=_hdr(owner)).json()["users"]
    analyst = next(u for u in users if u["email"] == roles.email("analyst"))

    # The analyst's own token, minted while they were an analyst.
    token = roles["analyst"]
    assert app_client.get("/api/investigations", headers=_hdr(token)).status_code == 200

    r = app_client.patch(
        f"/api/auth/users/{analyst['id']}", json={"role": "citizen"}, headers=_hdr(owner)
    )
    assert r.status_code == 200
    # The old token is revoked outright by the role change — and even if it were
    # not, it would resolve to a citizen.
    assert app_client.get("/api/auth/me", headers=_hdr(token)).status_code == 401


# ---------------------------------------------------------------------------
# §38 — what each role can and cannot reach
# ---------------------------------------------------------------------------

#: (path, roles that must get 200, roles that must get 403). Every role in
#: `ROLES` appears in one column or the other for every row, so a role added
#: later fails this table rather than silently defaulting to "allowed".
MATRIX = [
    ("/api/auth/users", {"admin", "owner"}, {"citizen", "viewer", "researcher", "analyst", "police"}),
    ("/api/audit", {"admin", "owner"}, {"citizen", "viewer", "researcher", "analyst", "police"}),
    ("/api/orgs", {"owner"}, {"citizen", "viewer", "researcher", "analyst", "police", "admin"}),
    (
        "/api/intel/clusters",
        {"viewer", "analyst", "police", "admin", "owner"},
        {"citizen", "researcher"},
    ),
    (
        "/api/intel/stats",
        {"citizen", "viewer", "researcher", "analyst", "police", "admin", "owner"},
        set(),
    ),
    (
        "/api/research/overview",
        {"researcher", "admin", "owner"},
        {"citizen", "viewer", "analyst", "police"},
    ),
    (
        "/api/investigations",
        {"citizen", "viewer", "analyst", "police", "admin", "owner"},
        {"researcher"},
    ),
]


@pytest.mark.parametrize(("path", "allowed", "refused"), MATRIX)
def test_route_matrix(app_client, roles, path, allowed, refused):
    assert allowed | refused == set(ROLES), (
        f"{path}: every role must be listed as allowed or refused; "
        f"missing {set(ROLES) - (allowed | refused)}"
    )
    for role in sorted(allowed):
        r = app_client.get(path, headers=_hdr(roles[role]))
        assert r.status_code == 200, f"{role} should reach {path}, got {r.status_code}"
    for role in sorted(refused):
        r = app_client.get(path, headers=_hdr(roles[role]))
        assert r.status_code == 403, f"{role} should be refused {path}, got {r.status_code}"


def test_a_citizen_cannot_erase_an_investigation(app_client, roles):
    r = app_client.delete("/api/investigations/AEG-000000000000", headers=_hdr(roles["citizen"]))
    assert r.status_code == 403


def test_a_researcher_response_carries_no_identifier(app_client, roles):
    """§27, checked on the bytes rather than trusted to the handler."""
    body = app_client.get("/api/research/overview", headers=_hdr(roles["researcher"])).json()
    text = repr(body)
    assert "@" not in text, "an email address reached the research surface"
    assert "case_id" not in text
    assert "AEG-" not in text
    assert body["privacy"]["min_cluster_size"] >= 3


# ---------------------------------------------------------------------------
# Ownership — the check tenancy cannot make
# ---------------------------------------------------------------------------


def _submit(client, token, text):
    r = client.post("/api/investigations", json={"text": text}, headers=_hdr(token))
    assert r.status_code == 202, r.text
    return r.json()["case_id"]


def test_a_citizen_cannot_read_another_citizens_investigation(app_client, roles):
    """The §39 line 'citizen accessing another user's investigation'.

    Both citizens are in the same organisation, which is the point: tenancy
    alone would have let this through.
    """
    owner = roles["owner"]
    second = f"second.{next(_serial)}@aegis.test"
    assert app_client.post(
        "/api/auth/users",
        json={"email": second, "password": PASSWORD, "role": "citizen"},
        headers=_hdr(owner),
    ).status_code == 201
    other = _login(app_client, second)

    case_id = _submit(app_client, roles["citizen"], "Your KYC is suspended, call 9876543210")

    # The owner submitted nothing; the citizen sees exactly their own case.
    mine = app_client.get("/api/investigations", headers=_hdr(roles["citizen"])).json()
    assert [c["case_id"] for c in mine["investigations"]] == [case_id]
    assert mine["scope"] == "own"

    theirs = app_client.get("/api/investigations", headers=_hdr(other)).json()
    assert theirs["investigations"] == []

    # And the direct read is a 404, not a 403 — a 403 would confirm the id.
    for path in ("", "/report", "/trace"):
        r = app_client.get(f"/api/investigations/{case_id}{path}", headers=_hdr(other))
        assert r.status_code == 404, (path, r.status_code)


def test_an_investigator_sees_the_organisations_case_book(app_client, roles):
    """The other half: `INVESTIGATION_READ_ALL` is what makes a queue a queue."""
    case_id = _submit(app_client, roles["citizen"], "Pay 4999 to renew your electricity meter")
    listing = app_client.get("/api/investigations", headers=_hdr(roles["police"])).json()
    assert listing["scope"] == "organisation"
    assert case_id in [c["case_id"] for c in listing["investigations"]]
    assert app_client.get(
        f"/api/investigations/{case_id}", headers=_hdr(roles["police"])
    ).status_code == 200


def test_a_citizen_sees_only_their_own_saved_reports(app_client, roles):
    listing = app_client.get("/api/reports", headers=_hdr(roles["citizen"]))
    assert listing.status_code == 200
    assert listing.json()["reports"] == []


# ---------------------------------------------------------------------------
# §19 — no path from sign-up or user admin to a higher role
# ---------------------------------------------------------------------------


def test_signup_always_creates_a_citizen_whatever_the_body_says(app_client):
    r = app_client.post(
        "/api/auth/signup",
        json={
            "full_name": "Escalation Attempt",
            "email": f"escalate.{next(_serial)}@aegis.test",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "accept_terms": True,
            # Not a field on the model. Sent anyway, which is what an attacker
            # does, and ignored — which is what the absence of the field means.
            "role": "admin",
        },
    )
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "citizen"


def test_an_admin_cannot_mint_an_owner_or_another_admin(app_client, roles):
    for role in ("owner", "admin"):
        r = app_client.post(
            "/api/auth/users",
            json={"email": f"sneaky.{role}.{next(_serial)}@aegis.test",
                  "password": PASSWORD, "role": role},
            headers=_hdr(roles["admin"]),
        )
        assert r.status_code == 403, role


def test_nobody_can_promote_themselves(app_client, roles):
    owner = roles["owner"]
    users = app_client.get("/api/auth/users", headers=_hdr(owner)).json()["users"]
    admin_row = next(u for u in users if u["email"] == roles.email("admin"))
    r = app_client.patch(
        f"/api/auth/users/{admin_row['id']}", json={"role": "owner"}, headers=_hdr(roles["admin"])
    )
    assert r.status_code == 403


def test_a_police_account_cannot_manage_users_at_all(app_client, roles):
    """§25: 'Cannot arbitrarily become admin.'"""
    assert app_client.get("/api/auth/users", headers=_hdr(roles["police"])).status_code == 403
    assert app_client.post(
        "/api/auth/users",
        json={"email": f"police.made.{next(_serial)}@aegis.test",
              "password": PASSWORD, "role": "admin"},
        headers=_hdr(roles["police"]),
    ).status_code == 403


def test_a_user_cannot_edit_their_own_role_through_the_profile_route(app_client, roles):
    """PATCH /api/auth/me accepts a name and a phone. A role sent alongside is
    not a field on the model, so it cannot be written by any code path."""
    r = app_client.patch(
        "/api/auth/me",
        json={"full_name": "Renamed Citizen", "role": "owner", "disabled": False},
        headers=_hdr(roles["citizen"]),
    )
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "citizen"
    assert r.json()["user"]["full_name"] == "Renamed Citizen"


# ---------------------------------------------------------------------------
# §39 — credentials, sessions, and the back button
# ---------------------------------------------------------------------------


def test_duplicate_signup_is_refused(app_client):
    body = {
        "full_name": "First Arrival",
        "email": f"duplicate.{next(_serial)}@aegis.test",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "accept_terms": True,
    }
    assert app_client.post("/api/auth/signup", json=body).status_code == 201
    assert app_client.post("/api/auth/signup", json=body).status_code == 409


@pytest.mark.parametrize(
    "password",
    [
        "short",             # under the length floor
        "password123",       # on the common list
        "aaaaaaaaaaaa",      # too few distinct characters
        "weakpass@aegis",    # contains the email's local part
    ],
)
def test_a_weak_password_is_refused_at_signup(app_client, password):
    r = app_client.post(
        "/api/auth/signup",
        json={
            "full_name": "Weak Password",
            "email": "weakpass@aegis.test",
            "password": password,
            "confirm_password": password,
            "accept_terms": True,
        },
    )
    assert r.status_code == 422, password


def test_mismatched_passwords_are_refused(app_client):
    r = app_client.post(
        "/api/auth/signup",
        json={
            "full_name": "Mismatch",
            "email": f"mismatch.{next(_serial)}@aegis.test",
            "password": PASSWORD,
            "confirm_password": PASSWORD + "x",
            "accept_terms": True,
        },
    )
    assert r.status_code == 422


def test_an_invalid_email_is_refused(app_client):
    r = app_client.post(
        "/api/auth/signup",
        json={
            "full_name": "Bad Email",
            "email": "not-an-email",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "accept_terms": True,
        },
    )
    assert r.status_code == 422


def test_logout_actually_ends_the_session(app_client, roles):
    """'logout then back-button access'. The browser's history still holds the
    page; the token behind it must be dead."""
    token = roles["citizen"]
    assert app_client.get("/api/auth/me", headers=_hdr(token)).status_code == 200
    assert app_client.post("/api/auth/logout", headers=_hdr(token)).status_code == 200
    assert app_client.get("/api/auth/me", headers=_hdr(token)).status_code == 401
    assert app_client.get("/api/investigations", headers=_hdr(token)).status_code == 401


def test_signing_out_everywhere_keeps_the_current_session(app_client, roles):
    first = roles["citizen"]
    second = _login(app_client, roles.email("citizen"))
    assert second and second != first

    sessions = app_client.get("/api/auth/sessions", headers=_hdr(second)).json()["sessions"]
    assert len(sessions) >= 2

    assert app_client.delete("/api/auth/sessions", headers=_hdr(second)).json()["revoked"] >= 1
    assert app_client.get("/api/auth/me", headers=_hdr(second)).status_code == 200
    assert app_client.get("/api/auth/me", headers=_hdr(first)).status_code == 401


def test_refresh_rotates_the_token_and_retires_the_old_one(app_client, roles):
    old = roles["viewer"]
    new = app_client.post("/api/auth/refresh", headers=_hdr(old)).json()["token"]
    assert new != old
    assert app_client.get("/api/auth/me", headers=_hdr(new)).status_code == 200
    assert app_client.get("/api/auth/me", headers=_hdr(old)).status_code == 401


def test_disabling_an_account_ends_its_sessions_and_refuses_a_new_login(app_client, roles):
    owner = roles["owner"]
    users = app_client.get("/api/auth/users", headers=_hdr(owner)).json()["users"]
    row = next(u for u in users if u["email"] == roles.email("viewer"))

    assert app_client.patch(
        f"/api/auth/users/{row['id']}", json={"disabled": True}, headers=_hdr(owner)
    ).status_code == 200

    assert app_client.get("/api/auth/me", headers=_hdr(roles["viewer"])).status_code == 401
    r = app_client.post(
        "/api/auth/login", json={"email": roles.email("viewer"), "password": PASSWORD}
    )
    assert r.status_code == 403


def test_changing_a_password_ends_every_other_session(app_client, roles):
    keep = roles["analyst"]
    other = _login(app_client, roles.email("analyst"))
    r = app_client.post(
        "/api/auth/password/change",
        json={
            "current_password": PASSWORD,
            "new_password": "another-quiet-harbour-91",
            "confirm_password": "another-quiet-harbour-91",
        },
        headers=_hdr(keep),
    )
    assert r.status_code == 200
    assert app_client.get("/api/auth/me", headers=_hdr(keep)).status_code == 200
    assert app_client.get("/api/auth/me", headers=_hdr(other)).status_code == 401
    assert _login(app_client, roles.email("analyst")) is None
    assert _login(app_client, roles.email("analyst"), "another-quiet-harbour-91")


def test_changing_a_password_needs_the_current_one(app_client, roles):
    r = app_client.post(
        "/api/auth/password/change",
        json={
            "current_password": "not-the-right-one",
            "new_password": "another-quiet-harbour-91",
            "confirm_password": "another-quiet-harbour-91",
        },
        headers=_hdr(roles["police"]),
    )
    assert r.status_code == 403


def test_password_reset_is_single_use_and_the_endpoint_is_not_an_oracle(app_client, roles):
    """The reset round trip, plus §30's 'do not expose password reset tokens'.

    `AEGIS_DEV_PASSWORD_RESET` is off in this fixture *and* enforcement is on,
    so the response must not carry a token; the test reaches into the store for
    one, which is what an operator reading the server log does.
    """
    from services.api.auth import issue_password_reset
    from services.api.db import SessionLocal
    from services.api.models_db import User

    known = app_client.post("/api/auth/password/forgot", json={"email": roles.email("citizen")})
    unknown = app_client.post("/api/auth/password/forgot", json={"email": "ghost@aegis.test"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json(), "the response must not distinguish the two"
    assert "dev_token" not in known.json()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == roles.email("citizen")).one()
        token = issue_password_reset(db, user)
    finally:
        db.close()

    new = "reset-quiet-harbour-42"
    r = app_client.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": new, "confirm_password": new},
    )
    assert r.status_code == 200
    assert _login(app_client, roles.email("citizen"), new)

    # Replay is refused.
    again = app_client.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": new, "confirm_password": new},
    )
    assert again.status_code == 400


def test_an_unknown_reset_token_is_refused(app_client):
    r = app_client.post(
        "/api/auth/password/reset",
        json={
            "token": "x" * 43,
            "new_password": "another-quiet-harbour-91",
            "confirm_password": "another-quiet-harbour-91",
        },
    )
    assert r.status_code == 400


def test_the_demo_roster_endpoint_is_silent_when_auth_is_enforced(app_client):
    """A deployment that enforces auth must not have an endpoint that lists
    accounts and hands out their shared password."""
    body = app_client.get("/api/auth/demo-accounts").json()
    assert body["open_mode"] is False
    assert body["accounts"] == []
    assert body["password"] is None


def test_no_response_ever_carries_a_password_hash(app_client, roles):
    """`User.as_public()` is the only projection, so this is a property of the
    code — asserted anyway, on the bytes, across every route that returns a user."""
    for path in ("/api/auth/me", "/api/auth/users", "/api/auth/sessions"):
        body = app_client.get(path, headers=_hdr(roles["owner"])).text
        assert "password_hash" not in body
        assert "pbkdf2" not in body
        assert "$argon2" not in body
