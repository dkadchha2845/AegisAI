"""
English scams are caught, and routine messages that share their words are not
(audit B-08, B-04).

B-08 was a textbook English customs scam — "Pay the clearance fine of 4999 now
or a police case will be filed" — read LIKELY_LEGITIMATE, because every
mechanical check that floors a score was written in Hinglish. Measuring it
found the opposite failure in the same checks: single words ("transfer",
"deposit", "confidential", a credential named in a warning) floored genuine
bank calls, a fixed-deposit notice and a friend's dinner-money request at
87-95.

The probe sets in `ml/data/probes/` are scored through `analyze_text`, the way
the Analyze page scores them. The floors below are the measured result when
these rules were written (`ml/evaluation/eval_probes.py`); a change that drops
under one is a regression, and a change that raises one should raise the floor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from services.api.engine.analyzer import analyze_text
from services.api.engine.classifier import LexicalStageClassifier
from services.api.engine.passport import TrustPassport

PROBES = Path(__file__).resolve().parents[3] / "ml" / "data" / "probes"


def _load(name: str) -> List[Dict[str, Any]]:
    path = PROBES / f"english_{name}.jsonl"
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def _fails(text: str) -> List[str]:
    passport = TrustPassport()
    passport.observe(text)
    return [c.name for c in passport.snapshot().checks if c.verdict == "FAIL"]


@pytest.mark.parametrize("name", ["dev", "heldout"])
def test_no_benign_probe_is_flagged(name: str) -> None:
    flagged = [
        (row["kind"], analyze_text(row["text"]).score)
        for row in _load(name)
        if not row["is_scam"]
    ]
    assert all(score < 40 for _, score in flagged), [f for f in flagged if f[1] >= 40]


@pytest.mark.parametrize("name, floor", [("dev", 7), ("heldout", 8)])
def test_scam_recall_does_not_regress(name: str, floor: int) -> None:
    caught = sum(
        analyze_text(row["text"]).score >= 40 for row in _load(name) if row["is_scam"]
    )
    assert caught >= floor


def test_the_b08_message_is_a_likely_scam() -> None:
    result = analyze_text(
        "This is FedEx customs. A parcel in your name contains illegal items. "
        "Pay the clearance fine of 4999 now or a police case will be filed."
    )
    assert result.verdict == "LIKELY_SCAM"
    assert any(f["label"] == "Procedural plausibility" for f in result.findings)


def test_the_payment_turn_is_staged_as_payment() -> None:
    """B-04: the turn naming the "safe account" is the one a warning is for."""
    pred = LexicalStageClassifier().predict("Abhi 50000 RBI safe account mein transfer kariye")
    assert pred.label == "PAYMENT_SETUP"


@pytest.mark.parametrize(
    "text",
    [
        "Pay the clearance fine of 4999 now or a police case will be filed.",
        "Transfer 25,000 now or a non-bailable warrant will be issued against you.",
        "Abhi 50000 transfer karo warna arrest ho jayega.",
        "A case will be registered and you will be arrested unless you pay today.",
        # A dot inside the VPA is not the end of the sentence.
        "Pay 4999 now to fedex.customs@okaxis or a police case will be filed.",
    ],
)
def test_payment_on_pain_of_arrest_is_conclusive(text: str) -> None:
    assert "Procedural plausibility" in _fails(text)


@pytest.mark.parametrize(
    "text",
    [
        # Civil consequences are real: e-challans and tax notices say these.
        "Pay within 60 days or the challan will be sent to the virtual court.",
        "Pay the outstanding demand by 30 Oct or legal action may follow.",
        # A warning names both halves and asks for neither.
        "Never pay anyone who threatens arrest, and report it on 1930.",
    ],
)
def test_civil_consequences_and_warnings_are_not_threats(text: str) -> None:
    assert "Procedural plausibility" not in _fails(text)


@pytest.mark.parametrize(
    "text, check",
    [
        # Each of these floored a genuine message at 87-95 before B-08.
        ("Your OTP for login is 482913.", "Credential request"),
        ("Bas OTP dikhana padega jo aapke phone par aaya hai.", "Credential request"),
        ("Suniye meri baat, kisi ko koi otp mat dena!", "Credential request"),
        ("Koi call pe OTP wagera maange toh mat dena, hum log nahi maangte.", "Credential request"),
        ("Main aapse OTP, PIN ya card number kabhi nahi poochungi.", "Credential request"),
        ("Koi OTP ya card details nahi chahiye hume.", "Credential request"),
        ("Your fixed deposit has been opened.", "Payment to individual"),
        ("Can you transfer my share of the dinner to my account? No hurry.", "Payment to individual"),
        ("Aap hold kijiye sir, main line transfer kar raha hoon.", "Payment to individual"),
        ("Jaldi nahi hai mummy, kal parso bhej dena.", "Payment to individual"),
        ("NetBank will never ask for your confidential details.", "Secrecy demand"),
    ],
)
def test_routine_words_do_not_floor_a_genuine_message(text: str, check: str) -> None:
    assert check not in _fails(text)


@pytest.mark.parametrize(
    "text, check",
    [
        ("Read me the OTP you just received.", "Credential request"),
        ("OTP bata dijiye sir, jaldi.", "Credential request"),
        ("Transfer the amount to the RBI safe account for verification.", "Payment to individual"),
        ("Aapko ek safe custody account mein transfer karna hoga.", "Payment to individual"),
        ("Withdrawal se pehle 48% tax pre-deposit karna padta hai.", "Payment to individual"),
        ("To release the prize, pay the processing fee of 12,500.", "Payment to individual"),
        ("This matter is strictly confidential.", "Secrecy demand"),
        ("Do not tell anyone about this call.", "Secrecy demand"),
        ("Kisi ko mat batana.", "Secrecy demand"),
    ],
)
def test_the_scam_forms_still_fail(text: str, check: str) -> None:
    assert check in _fails(text)
