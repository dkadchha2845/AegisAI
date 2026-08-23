"""
Measured metrics stay tied to the model they describe.

This project has been bitten twice by a metrics file drifting from its model:
a stale `backend_comparison.json` pinned serving to the lexical fallback for
weeks, and `stage-classifier/metrics.json` still claims macro-F1 0.269 for a
checkpoint that measures 0.767.

The full integrity check hashes ~950 MB and belongs in `make verify-checkpoint`,
not in a suite that has to stay fast. What is cheap — and what would have caught
both incidents — is asserting that the files which *do* live in git agree with
each other. Two records of the same evaluation disagreeing is the tell.

Everything here skips cleanly when the artifacts are absent, which is the normal
state on CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ARTIFACTS = Path(__file__).resolve().parents[3] / "ml" / "artifacts"
COMPARISON = ARTIFACTS / "backend_comparison.json"
MANIFEST = ARTIFACTS / "checkpoint_manifest.json"


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} absent (clean clone / CI)")
    return json.loads(path.read_text())


def test_manifest_has_the_expected_shape():
    m = _load(MANIFEST)
    assert m["schema"] == 1
    assert m["measured_at"]
    assert m["evaluation"]["split"]
    assert m["evaluation"]["n_examples"] > 0
    assert m["evaluation"]["results"], "manifest records no scores"


def test_manifest_carries_a_fingerprint():
    """Without this, the manifest is just another file that can go stale."""
    fp = _load(MANIFEST)["fingerprint"]
    assert fp["combined_sha256"]
    assert fp["files"], "no per-file hashes recorded"
    for name, rec in fp["files"].items():
        assert len(rec["sha256"]) == 64, name
        assert rec["bytes"] > 0, name


def test_manifest_agrees_with_the_promotion_gate():
    """The two committed records of the same evaluation must not disagree.

    This is the cheap version of the integrity check, and it is the assertion
    that would have caught the original stale-comparison incident.
    """
    manifest = _load(MANIFEST)
    comparison = _load(COMPARISON)

    recorded = manifest["evaluation"]["results"]
    assert set(recorded) == set(comparison), (
        f"manifest scores {sorted(recorded)} but backend_comparison has "
        f"{sorted(comparison)} — one of them is stale"
    )
    for backend, scores in comparison.items():
        assert recorded[backend]["macro_f1"] == pytest.approx(scores["macro_f1"]), (
            f"{backend}: manifest says {recorded[backend]['macro_f1']:.4f}, "
            f"backend_comparison says {scores['macro_f1']:.4f}. Re-run "
            f"ml/evaluation/eval_backends.py."
        )


def test_promoted_backend_actually_won():
    """Whatever is recorded as best must be the highest scorer.

    Guards the promotion gate's own logic, not just its inputs.
    """
    comparison = _load(COMPARISON)
    if len(comparison) < 2:
        pytest.skip("only one backend measured")
    best = max(comparison, key=lambda k: comparison[k]["macro_f1"])
    assert comparison[best]["macro_f1"] >= max(
        s["macro_f1"] for s in comparison.values()
    )


def test_recorded_scores_are_plausible():
    """A macro-F1 outside [0, 1] means something wrote garbage."""
    for backend, scores in _load(COMPARISON).items():
        assert 0.0 <= scores["macro_f1"] <= 1.0, backend
        assert 0.0 <= scores["weighted_f1"] <= 1.0, backend
