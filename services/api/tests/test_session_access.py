"""
A live session is reachable only by whoever opened it (audit S-07).

The session id is in every URL and every frame. Before S-07 it was the only
thing the session routes asked for, so anyone holding an id could read the
call's transcript, drive the session and download its evidence package. Now a
session answers to its token (returned once, at creation), its signed-in
creator, or staff who may read every case — and says "no such session" to
anyone else.

These run with authentication enforced, which is the default since S-01.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api import auth as auth_mod
from services.api.db import SessionLocal, init_db
from services.api.main import app


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(auth_mod, "auth_enabled", lambda: True)
    init_db()
    db = SessionLocal()
    try:
        auth_mod.seed_admin(db)
    finally:
        db.close()
    return TestClient(app)


def _start(client: TestClient):
    r = client.post("/api/session", json={"caller_number": "+18382247719"})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["session_id"], body["session_token"]


def test_starting_a_session_needs_no_account_and_returns_a_token(client) -> None:
    sid, token = _start(client)
    assert sid and len(token) >= 32


def test_the_id_alone_reads_nothing(client) -> None:
    sid, _ = _start(client)
    for method, path in (
        ("get", f"/api/session/{sid}"),
        ("get", f"/api/session/{sid}/report"),
        ("get", f"/api/session/{sid}/report.pdf"),
        ("post", f"/api/session/{sid}/investigate"),
        ("delete", f"/api/session/{sid}"),
    ):
        r = getattr(client, method)(path)
        # 404, not 403: a session you may not read is not confirmed to exist.
        assert r.status_code == 404, (path, r.status_code)
    r = client.post(f"/api/session/{sid}/utterance", json={"text": "Main CBI se bol raha hoon"})
    assert r.status_code == 404


def test_the_token_opens_it_by_header_or_by_query(client) -> None:
    sid, token = _start(client)
    assert client.get(f"/api/session/{sid}", headers={"X-Session-Token": token}).status_code == 200
    assert client.get(f"/api/session/{sid}/report?token={token}").status_code == 200
    r = client.post(
        f"/api/session/{sid}/utterance",
        json={"text": "Main CBI se bol raha hoon"},
        headers={"X-Session-Token": token},
    )
    assert r.status_code == 200
    assert r.json()["frame"]["session_id"] == sid


def test_another_sessions_token_does_not_open_it(client) -> None:
    sid_a, _ = _start(client)
    _, token_b = _start(client)
    r = client.get(f"/api/session/{sid_a}", headers={"X-Session-Token": token_b})
    assert r.status_code == 404


def test_listing_every_session_is_for_staff(client) -> None:
    _start(client)
    assert client.get("/api/session").status_code == 401
    login = client.post(
        "/api/auth/login", json={"email": "admin@aegis.local", "password": "changeme"}
    )
    assert login.status_code == 200
    staff = {"Authorization": f"Bearer {login.json()['token']}"}
    r = client.get("/api/session", headers=staff)
    assert r.status_code == 200 and r.json()["sessions"]


def test_the_creator_reaches_their_session_without_the_token(client) -> None:
    login = client.post(
        "/api/auth/login", json={"email": "admin@aegis.local", "password": "changeme"}
    )
    bearer = {"Authorization": f"Bearer {login.json()['token']}"}
    sid = client.post("/api/session", json={}, headers=bearer).json()["session_id"]
    assert client.get(f"/api/session/{sid}", headers=bearer).status_code == 200


def test_the_socket_needs_the_token(client) -> None:
    sid, token = _start(client)
    with client.websocket_connect(f"/api/session/ws/{sid}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error" and msg["code"] == "no_such_session"
    with client.websocket_connect(f"/api/session/ws/{sid}?token={token}") as ws:
        first = ws.receive_json()
        assert first.get("session_id") == sid and first.get("type") != "error"


def test_the_socket_refuses_payment_actions(client) -> None:
    """Releasing a payment hold is permission-checked and audited over REST.
    The socket used to accept it from anyone holding the socket, unaudited."""
    sid, token = _start(client)
    with client.websocket_connect(f"/api/session/ws/{sid}?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "guardian_approve_payment", "payload": {}})
        for _ in range(10):
            msg = ws.receive_json()
            if msg.get("type") == "error":
                assert msg["code"] == "use_rest"
                break
        else:  # pragma: no cover
            pytest.fail("the socket did not refuse the payment action")
