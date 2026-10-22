"""
Analyze and Investigate give the same score for the same evidence (T-20,
audit B-02).

Before T-20 a Hinglish digital-arrest message read 93 CRITICAL on
`/api/analyze/text`, *unscored* from `/api/investigations`, and ELEVATED from
the investigation's own fusion agent — three answers to one question. The
investigation now writes the analyzer's score, through the analyzer's own
floor function, tagged `score:uncalibrated`.
"""

from __future__ import annotations

import asyncio

import pytest

from schema.models import (
    EvidenceItem,
    InputType,
    InvestigationState,
    utc_now_iso,
)
from services.api import llm
from services.api.engine.analyzer import analyze_text
from services.api.orchestration import graph as orch

SCAMS = {
    "digital arrest": (
        "Main CBI officer bol raha hoon, aapke Aadhaar pe money laundering case hai. "
        "Abhi 50000 transfer karo warna arrest hoga, kisi ko mat batana."
    ),
    "customs (B-08)": (
        "This is FedEx customs. A parcel in your name contains illegal items. "
        "Pay the clearance fine of 4999 now or a police case will be filed."
    ),
    "kyc otp": (
        "Dear customer, your KYC has expired and your bank account will be blocked "
        "within 24 hours. Share the OTP you just received to update it."
    ),
    "qr refund": (
        "Ma'am, scan this QR code to receive your refund of 4,500. Enter your UPI PIN "
        "to complete the transaction now."
    ),
    "call transcript": (
        "CALLER: Hello, main Mumbai Cyber Crime se Inspector Rathore bol raha hoon.\n"
        "VICTIM: Ji, kya hua?\n"
        "CALLER: Aapke naam pe FIR darj hai. Disconnect mat kariye, video call on rakhiye.\n"
        "VICTIM: Main darr gaya hoon.\n"
        "CALLER: Abhi RBI safe account mein security deposit transfer kariye."
    ),
}
BENIGN = {
    "bank debit": (
        "Dear Customer, Rs 450.00 debited from A/c XX3421 on 24-08-26 to VPA "
        "grocerystore@ybl. Not you? Call 1800-11-2211. -SBI"
    ),
    "delivery": "Your Amazon order 402-8891 is out for delivery today between 2pm and 6pm.",
    "kyc reminder": (
        "Reminder from HDFC Bank: your KYC update is due. Visit your nearest branch "
        "with your documents. We will never ask for your OTP or PIN."
    ),
}


def _investigate(text: str) -> InvestigationState:
    state = InvestigationState(
        case_id="AEG-JUDGE",
        org_id="org-1",
        created_by="t@aegis.local",
        created_at=utc_now_iso(),
        inputs=[EvidenceItem(id="ev-01", kind=InputType.TEXT, text=text)],
        input_types=[InputType.TEXT],
    )
    return asyncio.run(orch.investigate(state))


@pytest.mark.parametrize("name", sorted({**SCAMS, **BENIGN}))
def test_the_investigation_scores_what_analyze_scores(name: str) -> None:
    text = {**SCAMS, **BENIGN}[name]
    done = _investigate(text)
    expected = analyze_text(text)
    assert done.risk_score == pytest.approx(expected.score, abs=0.05)
    assert done.risk_level is not None and done.risk_level.value == expected.level


@pytest.mark.parametrize("name", sorted(SCAMS))
def test_a_scam_is_scored_as_one_and_labelled_uncalibrated(name: str) -> None:
    done = _investigate(SCAMS[name])
    assert done.risk_score is not None and done.risk_score >= 70
    assert "score:uncalibrated" in done.degraded
    fusion = next(r for r in done.agent_results if r.agent == "threat_fusion")
    level = next(f.value for f in fusion.findings if f.label == "threat_level")
    # One answer: the agent's band is the state's band.
    assert level == done.risk_level.value


@pytest.mark.parametrize("name", sorted(BENIGN))
def test_a_benign_message_stays_below_the_warning_threshold(name: str) -> None:
    done = _investigate(BENIGN[name])
    assert done.risk_score is not None and done.risk_score < 25.0
    fusion = next(r for r in done.agent_results if r.agent == "threat_fusion")
    assert not [f for f in fusion.findings if f.label == "dispositive_check"]


def test_the_score_needs_no_language_model(monkeypatch) -> None:
    """Invariant 6: the LLM explains; it never scores."""

    def refuse(*args, **kwargs):
        raise AssertionError("the judge called a language model")

    for name in list(llm._BACKENDS):
        monkeypatch.setitem(llm._BACKENDS, name, refuse)
    monkeypatch.setattr(llm, "explain", refuse)
    monkeypatch.setattr(llm, "answer_question", refuse)
    done = _investigate(SCAMS["digital arrest"])
    assert done.risk_score is not None and done.risk_score >= 70
