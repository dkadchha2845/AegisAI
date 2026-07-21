"""
Number Spoofing Intelligence regressions.

Every case here is a claim the spoofing engine must keep making: a foreign
number wearing a CBI badge is a FAIL, a masked demo number is not punished for
being masked, and a clean personal mobile with no authority claim does not get
branded a scam just for existing. The last one is the false-positive direction
the whole product is careful about — a citizen's own number must not read HIGH.
"""

from __future__ import annotations

from services.api.engine.spoofing import analyze_number


def _verdicts(intel) -> dict[str, str]:
    return {c.name: c.verdict for c in intel.checks}


def test_no_number_is_unknown_not_clean():
    intel = analyze_number(None)
    assert intel.verdict == "UNKNOWN"
    assert intel.risk == 0.0
    # An absent number must never read as a passed check.
    assert all(c.verdict != "PASS" for c in intel.checks)


def test_international_number_claiming_indian_agency_fails():
    intel = analyze_number("+1 202 555 0143", claimed_identity="CBI Inspector Sharma")
    assert intel.verdict == "FAIL"
    assert intel.risk >= 70
    assert _verdicts(intel)["International routing"] == "FAIL"
    assert _verdicts(intel)["Caller-ID vs claimed authority"] == "FAIL"


def test_personal_mobile_claiming_authority_is_the_signature_mismatch():
    intel = analyze_number("+91 98765 43210", claimed_identity="main CBI se bol raha hoon")
    assert _verdicts(intel)["Caller-ID vs claimed authority"] == "FAIL"
    assert intel.verdict == "FAIL"


def test_masked_demo_number_is_not_faulted_for_masking():
    # The number the live console dials. Masked by the carrier, not the caller.
    intel = analyze_number("+91 98XXXX1234")
    assert _verdicts(intel)["Number format"] == "UNKNOWN"


def test_masked_demo_number_still_catches_authority_mismatch():
    intel = analyze_number("+91 98XXXX1234", claimed_identity="Inspector, crime branch")
    assert _verdicts(intel)["Caller-ID vs claimed authority"] == "FAIL"


def test_clean_personal_mobile_no_claim_is_low_risk():
    # A citizen's ordinary number with nobody claiming to be the police.
    intel = analyze_number("+91 91234 56789")
    assert intel.risk < 25
    assert intel.verdict in {"PASS", "UNKNOWN"}
    # International routing passes (it is +91) and format passes.
    assert _verdicts(intel)["International routing"] == "PASS"


def test_reported_number_is_dispositive():
    intel = analyze_number("+91 99887 76655")
    assert _verdicts(intel)["Reported number"] == "FAIL"
    assert intel.verdict == "FAIL"
    assert intel.risk >= 60


def test_bare_ten_digit_indian_number_parses():
    intel = analyze_number("9123456789")
    assert _verdicts(intel)["Number format"] == "PASS"
    assert _verdicts(intel)["International routing"] == "PASS"


def test_repeated_calls_raise_frequency_flag():
    intel = analyze_number("+91 91234 56789", call_count=4)
    assert _verdicts(intel)["Call frequency"] == "FAIL"
