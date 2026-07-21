"""
Scam-script similarity regressions.

The value of this signal is that it fires on *paraphrases* — lines that share
no rare keyword with the template — and stays quiet on ordinary conversation.
Both directions are tested, because a script matcher that also lights up on a
delivery call is one that inflates the false-positive rate the whole product is
built to keep low.
"""

from __future__ import annotations

from services.api.engine.analyzer import analyze_text
from services.api.engine.scripts import get_script_matcher
from services.api.engine.threat import SCRIPT_MIN


def test_similarity_is_bounded_and_zero_on_empty():
    m = get_script_matcher()
    assert m.match("").similarity == 0.0
    hit = m.match("main CBI se inspector bol raha hoon")
    assert 0.0 <= hit.similarity <= 1.0


def test_paraphrased_script_scores_above_the_gate():
    m = get_script_matcher()
    hit = m.match("main CBI crime branch se officer bol raha hoon, badge verify kar lo")
    assert hit.similarity >= SCRIPT_MIN
    assert hit.label == "AUTHORITY_CLAIM"


def test_benign_line_stays_below_the_gate():
    m = get_script_matcher()
    # A genuine delivery call — shares no scam-script sentence structure.
    hit = m.match("sir aapka amazon order kal deliver hoga, address confirm kijiye")
    assert hit.similarity < SCRIPT_MIN


def test_analyzer_surfaces_a_script_match_driver():
    res = analyze_text(
        "Caller: aapke naam par parcel mila hai jisme drugs the, money laundering ka "
        "non-bailable case register ho gaya hai"
    )
    assert any(d["label"] == "Script match" for d in res.drivers)


def test_analyzer_no_script_driver_on_benign():
    res = analyze_text(
        "Caller: sir ye sirf ek reminder call hai, koi jaldi nahi, aap branch mein aa "
        "sakte hain, hum kabhi otp nahi maangte"
    )
    assert not any(d["label"] == "Script match" for d in res.drivers)
