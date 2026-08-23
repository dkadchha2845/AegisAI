"""
Case-record persistence + audit-log regressions.

Runs in the default open mode (no token needed — the request acts as the seeded
admin), which is enough to exercise save → list → read and to confirm the
high-value actions leave an audit trail. Enforcement itself is covered in
test_auth.py; here the concern is that the durable side actually persists what
it claims to.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.db import init_db
from services.api.main import app


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def _start_scam_session(client) -> str:
    sid = client.post("/api/session", json={"caller_number": "+1-838-224-7719"}).json()["session_id"]
    for text in [
        "main CBI se Inspector Sharma bol raha hoon badge 4471",
        "aapke naam par drugs parcel mila hai, arrest warrant hai",
        "kisi ko mat bataiye digital arrest hai disconnect mat kijiye",
    ]:
        client.post(f"/api/session/{sid}/utterance", json={"text": text, "speaker": "CALLER"})
    return sid


def test_save_then_list_then_read(client):
    sid = _start_scam_session(client)

    saved = client.post(f"/api/session/{sid}/report/save")
    assert saved.status_code == 201
    report_id = saved.json()["record"]["report_id"]
    assert report_id.startswith("AGIS-")

    listed = client.get("/api/reports")
    assert listed.status_code == 200
    assert any(r["report_id"] == report_id for r in listed.json()["reports"])

    fetched = client.get(f"/api/reports/{report_id}")
    assert fetched.status_code == 200
    # The saved package is the full evidence package, transcript and all.
    assert fetched.json()["package"]["call"]["caller_number"] == "+1-838-224-7719"
    assert fetched.json()["package"]["transcript"]


def test_save_unknown_session_is_404(client):
    assert client.post("/api/session/nope/report/save").status_code == 404


def test_read_unknown_report_is_404(client):
    assert client.get("/api/reports/AGIS-DOESNOTEXIST").status_code == 404


def test_export_is_audited(client):
    sid = _start_scam_session(client)
    report_id = client.post(f"/api/session/{sid}/report/save").json()["record"]["report_id"]

    events = client.get("/api/audit").json()["events"]
    exports = [e for e in events if e["action"] == "report.export" and e["target"] == report_id]
    assert exports, "saving a report must leave an audit event"


def test_payment_override_is_audited(client):
    sid = _start_scam_session(client)
    # Push a payment; at this threat it should be held, then override it.
    client.post(f"/api/session/{sid}/payment/attempt", json={"amount_inr": 450000})
    client.post(f"/api/session/{sid}/payment/approve")

    events = client.get("/api/audit").json()["events"]
    actions = {e["action"] for e in events}
    assert "payment.attempt" in actions
    assert "payment.override" in actions
