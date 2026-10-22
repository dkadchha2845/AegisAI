"""
The committed research results say what they claim (T-06, audit D-04).

`research/results/exp0_stage_classifier_leak.json` is produced by
`research/experiments/exp0_stage_classifier_leak.py`, which needs the 915 MB
checkpoint and so cannot run here. What can be checked without it: the file's
shape, that every cut's sizes add up, and that it still carries the numbers the
documents quote — so a re-run that changed them fails the suite rather than
quietly contradicting the audit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESULT = ROOT / "research" / "results" / "exp0_stage_classifier_leak.json"
BACKENDS = {"lexical@e123bd5", "lexical", "muril", "fused@e123bd5"}


@pytest.fixture(scope="module")
def result() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_the_file_has_its_shape(result) -> None:
    assert result["experiment"] == "exp0_stage_classifier_leak"
    assert result["checkpoint"]["fingerprint"]["combined_sha256"]
    assert set(result["splits"]) == {"published_test@e123bd5", "own_test@85a2aee"}
    for cuts in result["splits"].values():
        assert set(cuts) == {"all", "leaked", "unseen"}
        for cell in cuts.values():
            assert set(cell) == BACKENDS | {"n"}
            for name in BACKENDS:
                if cell["n"]:
                    assert set(cell[name]) == {"macro_f1", "accuracy"}
                    assert 0.0 <= cell[name]["macro_f1"] <= 1.0
                else:
                    assert cell[name] is None  # an empty cut has no score, not zero


def test_every_split_is_exactly_its_leaked_and_unseen_turns(result) -> None:
    for name, cuts in result["splits"].items():
        assert cuts["leaked"]["n"] + cuts["unseen"]["n"] == cuts["all"]["n"], name


def test_it_reproduces_the_published_figures(result) -> None:
    """The numbers docs/AUDIT.md B-01 and the README quote."""
    published = result["splits"]["published_test@e123bd5"]
    assert (published["all"]["n"], published["leaked"]["n"], published["unseen"]["n"]) == (423, 311, 112)
    assert published["all"]["muril"]["macro_f1"] == pytest.approx(0.767, abs=5e-4)
    assert published["leaked"]["muril"]["macro_f1"] == pytest.approx(1.0)
    assert published["unseen"]["muril"]["macro_f1"] == pytest.approx(0.300, abs=5e-4)
    assert published["unseen"]["lexical@e123bd5"]["macro_f1"] == pytest.approx(0.431, abs=5e-4)
    own = result["splits"]["own_test@85a2aee"]
    assert own["leaked"]["n"] == 0
    assert own["all"]["muril"]["macro_f1"] == pytest.approx(0.221, abs=5e-4)
    assert own["all"]["lexical@e123bd5"]["macro_f1"] == pytest.approx(0.372, abs=5e-4)
