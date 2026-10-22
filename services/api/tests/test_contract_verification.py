"""
A7's verdict has a place in the contract before any agent writes it (T-17).

The field is optional, so an investigation recorded before it existed still
validates; the enum agrees across Python and TypeScript; and the model holds
the verifier to its one rule — it may uphold, weaken or reject a finding, and
never strengthen one (docs/ARCHITECTURE.md §2.3).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from schema.models import Finding, InvestigationState, Verification, VerificationVerdict

ROOT = Path(__file__).resolve().parents[3]
#: The last commit before T-17 added the field.
BEFORE = "d0ca55c"


def test_an_investigation_recorded_before_t17_still_validates() -> None:
    raw = subprocess.run(
        ["git", "show", f"{BEFORE}:schema/mock-investigation.json"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    old = json.loads(raw)
    assert all(
        "verification" not in f for r in old["agent_results"] for f in r["findings"]
    ), "the old fixture should predate the field"
    state = InvestigationState.model_validate(old)
    assert all(f.verification is None for r in state.agent_results for f in r.findings)


def test_the_verdicts_agree_on_both_sides() -> None:
    ts = (ROOT / "schema" / "types.ts").read_text(encoding="utf-8")
    m = re.search(r"export const VERIFICATION_VERDICTS = \[(.*?)\] as const;", ts, re.S)
    assert m and re.findall(r'"([^"]+)"', m.group(1)) == [v.value for v in VerificationVerdict]


def _v(**kw) -> Verification:
    base = dict(
        verdict=VerificationVerdict.DOWNGRADED, reason="single agent, uncorroborated",
        challenger="deterministic:uncorroborated", confidence_before=0.9,
        confidence_after=0.6, weight=0.7,
    )
    return Verification(**{**base, **kw})


def test_each_verdict_has_its_shape() -> None:
    assert _v().weight == 0.7
    assert _v(verdict=VerificationVerdict.UPHELD, confidence_after=0.9, weight=1.0)
    assert _v(verdict=VerificationVerdict.REJECTED, confidence_after=0.0, weight=0.0)
    finding = Finding(label="x", source="t", verification=_v())
    assert Finding.model_validate(finding.model_dump()).verification == finding.verification


@pytest.mark.parametrize(
    "kw",
    [
        {"confidence_after": 0.95},                                   # raised confidence
        {"verdict": VerificationVerdict.UPHELD, "confidence_after": 0.9, "weight": 0.5},
        {"verdict": VerificationVerdict.UPHELD, "weight": 1.0},       # upheld but weakened
        {"verdict": VerificationVerdict.REJECTED, "weight": 0.2},     # rejected but counted
        {"weight": 1.0},                                              # downgraded but full weight
        {"weight": 0.0},                                              # downgraded to nothing
        {"reason": ""},                                               # no reason given
    ],
)
def test_a_verdict_that_breaks_the_rules_is_refused(kw) -> None:
    with pytest.raises(ValidationError):
        _v(**kw)
