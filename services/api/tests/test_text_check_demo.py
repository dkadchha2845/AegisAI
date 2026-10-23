"""
The text check gets the obvious cases right, both ways (T-77).

Reported by the owner on 2026-10-22: pasting the project's own brief into
Analyze read "95% scam". A document *about* scams named every scam ingredient
and was scored sentence by sentence as if a caller had said each one. Fixing
it found the opposite failure too: a work-from-home "registration fee" scam
read 7.5 and a loan-fee scam 24.6.

`ml/data/probes/demo.jsonl` holds 35 everyday cases — scams of ten kinds in
English and Hinglish, ordinary messages (with and without phone numbers),
bank and police warnings, and inputs too thin to judge. It was written while
fixing these rules, so it is a regression net and the demo script, not an
unbiased measurement; the unbiased ones are the held-out probes and the
corpus splits (`ml/evaluation/eval_probes.py`), which did not move.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.api.engine.analyzer import analyze_text, document_reason
from services.api.engine.passport import TrustPassport
from services.api.shield.verify import verify

ROOT = Path(__file__).resolve().parents[3]
DEMO = [json.loads(line) for line in (ROOT / "ml/data/probes/demo.jsonl").open(encoding="utf-8")]


@pytest.mark.parametrize("row", DEMO, ids=[r["kind"] for r in DEMO])
def test_each_demo_case_gets_the_right_answer(row) -> None:
    result = verify(text=row["text"])
    if row["expect"] == "scam":
        assert result["score"] >= 70 and result["verdict"] == "LIKELY_SCAM", result["score"]
    elif row["expect"] == "benign":
        assert result["score"] < 40, result["score"]
    else:
        assert result["verdict"] == "INSUFFICIENT"


@pytest.mark.parametrize("name", ["README.md", "AEGIS_AGENT_BRIEF.md", "docs/PRD.md"])
def test_a_document_about_scams_is_not_scored_as_one(name: str) -> None:
    result = verify(text=(ROOT / name).read_text(encoding="utf-8"))
    assert result["verdict"] == "INSUFFICIENT"
    assert "looks like a document" in result["summary"]


def test_a_long_call_transcript_is_never_refused_as_a_document() -> None:
    turns = "\n".join(
        f"Caller: line {i} — main CBI se bol raha hoon, aap digital arrest par hain.\nMe: ji" for i in range(60)
    )
    assert len(turns) > 2500 and document_reason(turns) is None
    assert analyze_text(turns).verdict == "LIKELY_SCAM"


def _fails(text: str) -> list[str]:
    passport = TrustPassport()
    passport.observe(text.lower())
    return [c.name for c in passport.snapshot().checks if c.verdict == "FAIL"]


def test_digital_arrest_counts_only_when_said_to_the_listener() -> None:
    assert "Secrecy demand" in _fails("Aap digital arrest par hain, video call on rakhiye.")
    assert "Secrecy demand" in _fails("You are under digital arrest until the inquiry ends.")
    assert _fails("Digital arrest scams defrauded citizens of 1,776 crore in 2024.") == []


@pytest.mark.parametrize(
    "warning",
    [
        "Never share your OTP or transfer money to a safe account. Report fraud on 1930.",
        "Beware of callers who say you are under digital arrest and must keep it confidential.",
        "No bank will ever ask you to pay a fine or a police case will be filed.",
    ],
)
def test_a_warning_names_the_scam_and_trips_nothing(warning: str) -> None:
    assert _fails(warning) == []
