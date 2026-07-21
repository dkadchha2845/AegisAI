"""
Evidence package + PDF regressions.

The package is the escalation artifact — if it silently drops the caller number,
the citations, or the transcript, the whole "auditable, submittable" claim is
hollow. These pin the structure and the two things a downstream reader most
needs: the named evidence, and a PDF that is actually a PDF.
"""

from __future__ import annotations

import pytest

from services.api.engine.report import build_evidence_package
from services.api.engine.report_pdf import pdf_available, render_pdf
from services.api.engine.session import Session


def _run_scam_call() -> Session:
    s = Session(caller_number="+1-838-224-7719", session_id="test-report")
    s.guardian_name = "Priya"
    for speaker, text in [
        ("CALLER", "main CBI Mumbai se Inspector Sharma bol raha hoon badge 4471"),
        ("VICTIM", "ji sir"),
        ("CALLER", "aapke naam par parcel mein drugs mila hai, arrest warrant hai"),
        ("CALLER", "kisi ko mat bataiye, digital arrest hai, disconnect mat kijiye"),
        ("CALLER", "verification ke liye OTP bataiye jo abhi aaya"),
    ]:
        s.ingest(text, speaker=speaker)
    return s


def test_package_has_the_load_bearing_fields():
    pkg = build_evidence_package(_run_scam_call())
    assert pkg["report_id"].startswith("KVCH-")
    assert pkg["call"]["caller_number"] == "+1-838-224-7719"
    assert pkg["assessment"]["claimed_identity"]  # a claim was detected
    assert pkg["incident"]["peak_threat"] > 0
    assert pkg["transcript"], "transcript must carry the underlying evidence"
    assert pkg["reporting_guidance"], "must tell the user how to escalate"


def test_package_surfaces_number_and_identity_evidence():
    pkg = build_evidence_package(_run_scam_call())
    categories = {e["category"] for e in pkg["evidence"]}
    assert "Caller number" in categories  # spoofing evidence present
    assert "Identity" in categories       # passport evidence present
    # The foreign number claiming an Indian agency must be flagged.
    assert pkg["assessment"]["caller_number_verdict"] == "FAIL"


def test_package_timeline_is_ordered_and_deduped():
    pkg = build_evidence_package(_run_scam_call())
    stages = [step["stage"] for step in pkg["stage_timeline"]]
    assert stages == list(dict.fromkeys(stages))  # no duplicate stage rows
    assert "AUTHORITY_CLAIM" in stages


def test_empty_call_still_produces_a_valid_package():
    pkg = build_evidence_package(Session(caller_number=None, session_id="empty"))
    assert pkg["report_id"]
    assert pkg["transcript"] == []
    assert pkg["evidence"] == []


@pytest.mark.skipif(not pdf_available(), reason="reportlab not installed")
def test_pdf_renders_to_pdf_bytes():
    pdf = render_pdf(build_evidence_package(_run_scam_call()))
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000
