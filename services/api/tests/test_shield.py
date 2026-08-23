"""
CFSRP (Module 3) regression tests.

The citizen shield's job is to be *right when it matters and quiet when it
doesn't*: escalate a real scam, stay calm on a genuine call (the low-false-
positive requirement the evaluation calls out), corroborate with Module 2 when
the infrastructure is known, and never put an un-vetted instruction in a
frightened person's hands.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.main import app
from services.api.shield import build_complaint, build_guidance, verify
from services.api.shield.response import build_response

DIGITAL_ARREST = (
    "Sir main CBI se bol raha hoon. Aapke Aadhaar par drugs ka parcel mila hai, "
    "non-bailable case hai. Digital arrest par hain aap, kisi ko mat bataiye. "
    "RBI supervised account cbi.verify@okaxis mein 50000 transfer kariye abhi."
)

BENIGN = (
    "Sir aapki credit card payment due hai, ye ek reminder call hai. Hum kabhi "
    "OTP nahi maangte. Aap apne time par branch mein aa sakte hain, koi jaldi nahi."
)


def test_verify_escalates_digital_arrest():
    r = verify(text=DIGITAL_ARREST, number="7042118830", claimed_identity="CBI", city="Bengaluru")
    assert r["verdict"] == "LIKELY_SCAM"
    assert r["level"] in ("HIGH", "CRITICAL")
    assert r["emergency"]["show_panic_banner"] is True
    assert r["guidance"]["actions"]


def test_verify_stays_calm_on_benign_call():
    """False-positive discipline: a genuine bank reminder must not read as a scam."""
    r = verify(text=BENIGN, city="Pune")
    assert r["verdict"] == "LIKELY_LEGITIMATE"
    assert r["level"] in ("CALM", "WATCH")
    assert r["emergency"]["show_panic_banner"] is False


def test_module2_corroboration_raises_confidence():
    """A known-fraud number should push a borderline artifact to LIKELY_SCAM even
    when the words alone are thin — the whole point of connecting the modules."""
    thin = verify(text="hello please call back", number="7042118830")
    assert thin["intel"]["known_infrastructure"] is True
    assert thin["verdict"] == "LIKELY_SCAM"


def test_unknown_number_is_not_invented_danger():
    """An unknown number must not manufacture a scam verdict from nothing."""
    r = verify(text="Hi, are we still meeting at 5?", number="9812345678")
    assert r["intel"]["known_infrastructure"] is False
    assert r["verdict"] in ("LIKELY_LEGITIMATE", "INSUFFICIENT", "SUSPICIOUS")


def test_guidance_is_stage_specific_and_verbatim():
    payment = build_guidance("PAYMENT_EXECUTION", "CRITICAL")
    greeting = build_guidance("GREETING", "WATCH")
    assert payment.actions != greeting.actions
    assert any("PIN" in a or "transaction" in a for a in payment.actions)


def test_emergency_response_scales_with_severity():
    urgent = build_response("CRITICAL", "PAYMENT_EXECUTION", payment_risk=True)
    calm = build_response("CALM", "GREETING", payment_risk=False)
    assert urgent.severity == "urgent" and urgent.show_panic_banner
    assert calm.severity == "info" and not calm.show_panic_banner
    assert any(h["value"] == "1930" for h in urgent.helplines)


def test_complaint_extracts_entities_and_links():
    r = verify(text=DIGITAL_ARREST, number="7042118830", city="Bengaluru")
    c = build_complaint(r, submitted_text=DIGITAL_ARREST, city="Bengaluru")
    assert c["complaint_id"].startswith("AGIS-CIT-")
    assert "cbi.verify@okaxis" in c["entities"]["upi_ids"]
    assert c["linked_intelligence"]["clusters"], "should link to a known cluster"


def test_shield_routes_public_and_vault_token_gated():
    with TestClient(app) as client:
        # Verify needs no auth.
        r = client.post("/api/shield/verify", json={"text": DIGITAL_ARREST, "number": "7042118830"})
        assert r.status_code == 200

        # Preserve returns a token.
        r = client.post("/api/shield/preserve", json={"text": DIGITAL_ARREST, "number": "7042118830", "city": "Bengaluru"})
        assert r.status_code == 201
        token = r.json()["token"]

        # The vault is reachable with the token…
        assert client.get(f"/api/shield/vault/{token}").status_code == 200
        assert client.get(f"/api/shield/vault/{token}/complaint").status_code == 200
        # …and not with a wrong one.
        assert client.get("/api/shield/vault/not-a-real-token").status_code == 404


def test_verify_requires_some_input():
    with TestClient(app) as client:
        r = client.post("/api/shield/verify", json={"text": "", "number": None, "upi": None})
        assert r.status_code == 422
