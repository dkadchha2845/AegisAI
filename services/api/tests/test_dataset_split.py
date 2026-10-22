"""
The committed splits are disjoint in every way that would let a model cheat
(audit B-07).

The previous split held out call *skeletons* and was described as
leave-archetypes-out. Three archetypes have more than one skeleton, so one sat
in all three splits and two more in both validation and test — any figure
measured on it was partly measured on scam types the model had trained on.
These assertions run on the files in `ml/data/processed/`, so a rebuilt split
that breaks them fails the suite rather than producing a number.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

import pytest

PROCESSED = Path(__file__).resolve().parents[3] / "ml" / "data" / "processed"
SPLITS = ("train", "val", "test")
LABELS = {
    "GREETING", "AUTHORITY_CLAIM", "FEAR_INDUCTION", "ISOLATION",
    "VERIFICATION_DEMAND", "PAYMENT_SETUP", "PAYMENT_EXECUTION", "BENIGN",
}


@pytest.fixture(scope="module")
def rows() -> Dict[str, List[dict]]:
    out = {}
    for name in SPLITS:
        path = PROCESSED / f"{name}.jsonl"
        if not path.exists():
            pytest.skip(f"{path} absent")
        out[name] = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


@pytest.mark.parametrize("field", ["archetype", "call_id"])
def test_no_archetype_or_call_is_in_two_splits(rows, field) -> None:
    seen = {name: {r[field] for r in rows[name]} for name in SPLITS}
    for i, a in enumerate(SPLITS):
        for b in SPLITS[i + 1:]:
            shared = seen[a] & seen[b]
            assert not shared, f"{field} in both {a} and {b}: {sorted(shared)[:5]}"


def test_no_text_is_in_two_splits(rows) -> None:
    seen = {name: {_norm(r["text"]) for r in rows[name]} for name in SPLITS}
    for i, a in enumerate(SPLITS):
        for b in SPLITS[i + 1:]:
            assert not (seen[a] & seen[b]), f"a turn's text is in both {a} and {b}"


def test_validation_and_test_cover_every_stage_and_both_classes(rows) -> None:
    for name in ("val", "test"):
        labels = {r["label"] for r in rows[name]}
        assert labels == LABELS, f"{name} is missing {sorted(LABELS - labels)}"
        assert any(r["is_scam"] for r in rows[name]) and any(not r["is_scam"] for r in rows[name])


def test_the_report_says_what_the_files_are(rows) -> None:
    report = (PROCESSED / "report.md").read_text(encoding="utf-8")
    assert "Every archetype (scam type) sits in exactly one split" in report
    for name in ("test", "val"):
        archetypes = sorted({r["archetype"] for r in rows[name]})
        line = next(l for l in report.splitlines() if l.startswith(f"- {name.capitalize()} archetypes"))
        for a in archetypes:
            assert f"`{a}`" in line, f"report omits {name} archetype {a}"


def test_the_model_card_counts_what_the_files_hold(rows) -> None:
    """The card used to say "320 synthetic calls" and "2 and 4 test examples"
    in prose, two splits after either was true (audit D-12)."""
    from services.api.main import THIN_CLASS, model_card

    text = " ".join(model_card()["limitations"])
    calls = {name: len({r["call_id"] for r in rows[name]}) for name in SPLITS}
    assert f"{sum(calls.values())} synthetic calls" in text
    for split, word in (("test", "test"), ("val", "validation")):
        counts: Dict[str, int] = {}
        for r in rows[split]:
            counts[r["label"]] = counts.get(r["label"], 0) + 1
        for label, n in counts.items():
            if n < THIN_CLASS:
                assert f"{label} has {n} {word} examples" in text
