"""
Entity extraction — the false negatives that cost a fraud link.

    .venv/bin/python -m pytest services/api/tests/test_entity_extraction.py -q

`intel/entities.py` is where an artifact becomes graph nodes. A missed entity is
not a cosmetic loss: it is a case that never connects to the three other cases
paying the same mule account, and the failure is invisible — no error, no log,
just an edge that is never drawn.

This file exists because of one such bug, found by running the agent layer
against the real extractor rather than against a fixture. Every case below is
either that bug or a neighbour of it that must not regress while fixing it.
"""

from __future__ import annotations

import pytest

from services.api.intel.entities import extract_from_text

# --------------------------------------------------------------------------
# The bug: a VPA at the end of the message
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        # The shape that was broken: the payment address is the last token,
        # which is how almost every real payment demand is written.
        ("Aapka KYC block ho gaya hai. Rs 10 bhejiye: sbi.kyc@okhdfcbank", "sbi.kyc@okhdfcbank"),
        ("Court fees ke liye payment kariye abhi. UPI ID: legal.dept@paytm", "legal.dept@paytm"),
        ("Refund ke liye confirm kijiye - refund.rbi@ybl", "refund.rbi@ybl"),
        ("cbi.verify@okaxis", "cbi.verify@okaxis"),
        # And the same VPA mid-sentence, which always worked.
        ("pay to cbi.verify@okaxis now", "cbi.verify@okaxis"),
        ("send it to verify@ybl today", "verify@ybl"),
    ],
)
def test_a_upi_id_is_found_wherever_it_sits(text: str, expected: str) -> None:
    """A VPA at the end of the text is not a fragment.

    The guard that rejects fragments tested `text[e:e+1] in "-."`. At the end of
    a string that slice is `""`, and `"" in "-."` is True in Python — the empty
    string is a substring of everything — so the match was thrown away.
    """
    assert expected in extract_from_text(text).upi_ids


def test_trailing_whitespace_was_never_the_difference() -> None:
    """The tell that made the bug findable: one trailing space fixed it."""
    without = extract_from_text("UPI: cbi.verify@okaxis")
    with_space = extract_from_text("UPI: cbi.verify@okaxis ")
    assert without.upi_ids == with_space.upi_ids == ["cbi.verify@okaxis"]


# --------------------------------------------------------------------------
# The neighbours the fix must not break
# --------------------------------------------------------------------------


def test_a_genuine_fragment_is_still_rejected() -> None:
    """The guard exists for a reason: `@gov` cut out of a longer address.

    Fixing the end-of-string case must not also accept the fragments the check
    was written to catch, or the graph fills with nodes like `cbi.helpdesk@gov`.
    """
    found = extract_from_text("write to cbi.helpdesk@gov-in-portal.com about it")
    assert found.upi_ids == []
    assert "cbi.helpdesk@gov-in-portal.com" in found.emails


def test_an_email_at_the_end_is_an_email_not_a_vpa() -> None:
    found = extract_from_text("Contact the officer at ravi.kumar@gmail.com")
    assert found.emails == ["ravi.kumar@gmail.com"]
    assert found.upi_ids == []


def test_a_consumer_mail_handle_is_classified_as_email() -> None:
    """`someone@gmail` has VPA shape but is not one."""
    found = extract_from_text("mail me: victim@gmail")
    assert found.upi_ids == []
    assert "victim@gmail" in found.emails


def test_a_domain_at_the_end_still_parses() -> None:
    found = extract_from_text("Update your details at sbi-secure-login.xyz")
    assert found.domains == ["sbi-secure-login.xyz"]
    assert found.upi_ids == []


def test_a_phone_number_at_the_end_still_parses() -> None:
    assert extract_from_text("Call back on 9876543210").phones == ["9876543210"]


def test_several_vpas_including_a_trailing_one() -> None:
    """A mule ring names more than one account — that is the whole point of the
    graph, and the last one in the list was exactly the one being dropped."""
    found = extract_from_text("Send half to first.mule@ybl and the rest to second.mule@paytm")
    assert found.upi_ids == ["first.mule@ybl", "second.mule@paytm"]


def test_benign_text_yields_no_payment_entities() -> None:
    """The false-positive case. A legitimate bank alert names no VPA, and the
    extractor must not manufacture one — a fabricated node is a fabricated
    fraud link, which is the one thing an evidence package cannot afford."""
    found = extract_from_text(
        "Rs 4,999 debited from A/c XX4471 towards SWIGGY on 24-08-26. "
        "Not you? Call the number on the back of your card."
    )
    assert found.upi_ids == []
    assert found.wallets == []
    assert found.domains == []
