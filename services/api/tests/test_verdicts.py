"""
Verdict regression tests.

    .venv/bin/python -m pytest services/api/tests -q

Every case here is one the engine got *wrong* at some point during
development, which is the only reason a case earns a place in this file. The
two failure modes are not symmetric and both are represented deliberately:

  - A missed scam is the obvious harm.
  - A false positive on a genuine bank call is the subtler one. It is how a
    user learns to dismiss the alert, and a system people dismiss protects
    nobody. The benign cases here — "we never ask for your OTP", a delivery
    notification, a payment reminder — all read as CRITICAL at some point.

The suite runs against the engine directly rather than over HTTP, so a failure
points at the logic instead of the transport.
"""

from __future__ import annotations

import pytest

from services.api.engine.analyzer import analyze_text
from services.api.engine.passport import _is_credential_request
from services.api.engine.upi import analyze_upi

SCAMS = [
    pytest.param(
        "Caller: main cyber crime se ACP Verma. Aapke naam par case hai. OTP bataiye.",
        id="credential-request",
    ),
    pytest.param(
        "Ye matter confidential hai, kisi ko mat bataiye. Call disconnect mat kariye.",
        id="isolation",
    ),
    pytest.param(
        # Both an isolation demand and a credential demand in one breath. The
        # advisory guard must not let "kisi ko mat bataiye" suppress the
        # genuine "OTP bataiye" beside it.
        "Ye matter confidential hai kisi ko mat bataiye, ab OTP bataiye jaldi.",
        id="isolation-plus-credential",
    ),
    pytest.param(
        "Sir refund ke liye ye QR scan kariye aur apna UPI PIN daaliye, paisa aa jayega.",
        id="pin-to-receive",
    ),
    pytest.param(
        "Verification ke liye RBI supervised account mein 4,50,000 transfer kariye.",
        id="refundable-deposit",
    ),
]

BENIGN = [
    pytest.param(
        "Sir aapki credit card payment due hai, reminder call hai. Hum kabhi OTP "
        "nahi maangte, branch mein aa sakte hain, koi jaldi nahi.",
        id="bank-warns-about-otp",
    ),
    pytest.param(
        "Never share your OTP or UPI PIN with anyone, including bank staff.",
        id="safety-advisory",
    ),
    pytest.param(
        "Your Amazon order 402-9931 ships tomorrow, track it in the app.",
        id="delivery-notification",
    ),
    pytest.param(
        "Aapka order kal deliver hoga, address confirm kar lijiye please.",
        id="delivery-confirmation",
    ),
]


@pytest.mark.parametrize("text", SCAMS)
def test_scam_is_flagged(text: str) -> None:
    result = analyze_text(text)
    assert result.verdict == "LIKELY_SCAM", f"{result.verdict} @ {result.score}"
    assert result.score >= 70
    # A verdict with no stated reason is one the user cannot check.
    assert result.findings or result.drivers
    assert result.citations


@pytest.mark.parametrize("text", BENIGN)
def test_benign_is_not_flagged(text: str) -> None:
    result = analyze_text(text)
    assert result.verdict != "LIKELY_SCAM", f"{result.score}: {result.findings}"
    assert result.score < 40


def test_short_input_is_insufficient_not_safe() -> None:
    """Absence of evidence must never be reported as evidence of safety."""
    result = analyze_text("hi")
    assert result.verdict == "INSUFFICIENT"


class TestCredentialAdvisory:
    def test_request_detected(self) -> None:
        assert _is_credential_request("apna otp bataiye")

    def test_warning_not_a_request(self) -> None:
        assert not _is_credential_request("hum kabhi otp nahi maangte")
        assert not _is_credential_request("never share your pin with anyone")

    def test_distant_negation_does_not_suppress(self) -> None:
        # The negation is about something else entirely and sits far from the
        # credential word; it must not licence the request beside it.
        assert _is_credential_request(
            "hum aapko pareshan nahi karna chahte the lekin ab bank ka otp bataiye"
        )


class TestUPI:
    def test_impersonating_local_part(self) -> None:
        analysis = analyze_upi("rbi.verify@okaxis")
        labels = [f.label for f in analysis.findings]
        assert "Impersonates an institution" in labels

    def test_payee_name_mismatch_beats_everything(self) -> None:
        analysis = analyze_upi(
            "upi://pay?pa=refund.cell@okaxis&pn=Ramesh%20Traders&am=450000",
            claimed_identity="RBI",
        )
        labels = [f.label for f in analysis.findings]
        assert "Payee name does not match claim" in labels
        assert analysis.amount == 450000

    def test_ordinary_vpa_is_not_condemned(self) -> None:
        """A normal personal VPA must not be called fraudulent. The absence of
        a red flag is not a green light either — hence INSUFFICIENT."""
        analysis = analyze_upi("rahul.sharma@oksbi")
        assert not [f for f in analysis.findings if f.verdict == "FAIL"]
        result = analyze_text("rahul.sharma@oksbi")
        assert result.verdict == "INSUFFICIENT"
