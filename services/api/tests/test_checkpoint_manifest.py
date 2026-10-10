"""
Measured metrics stay tied to the model they describe.

This project has been bitten twice by a metrics file drifting from its model:
a `backend_comparison.json` that disagreed with the checkpoint beside it, and
`stage-classifier/metrics.json`, which records macro-F1 0.269 for a different
training run from the weights on disk. (The 0.767 these notes once called the
checkpoint's real score was itself a train/test leak — docs/AUDIT.md, B-01.)

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
    assert m["schema"] == 2
    assert m["measured_at"]
    assert m["evaluation"]["split"]
    assert m["evaluation"]["n_examples"] > 0
    assert m["evaluation"]["status"] in ("valid", "refused")
    assert m["evaluation"]["reason"], "a manifest must say why it is valid or refused"
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

    assert manifest["evaluation"]["status"] == comparison["status"]
    assert manifest["evaluation"]["reason"] == comparison["reason"]
    assert manifest["evaluation"]["leak_check"] == comparison["leak_check"]

    recorded = manifest["evaluation"]["results"]
    scores = comparison["results"]
    assert set(recorded) == set(scores), (
        f"manifest scores {sorted(recorded)} but backend_comparison has "
        f"{sorted(scores)} — one of them is stale"
    )
    for backend, s in scores.items():
        assert recorded[backend]["macro_f1"] == pytest.approx(s["macro_f1"]), (
            f"{backend}: manifest says {recorded[backend]['macro_f1']:.4f}, "
            f"backend_comparison says {s['macro_f1']:.4f}. Re-run "
            f"ml/evaluation/eval_backends.py."
        )


def test_the_committed_comparison_scores_the_checkpoint_only_after_a_clean_leak_check():
    """The assertion that would have caught B-01, on the file that carried it.

    `backend_comparison.json` is tracked. Whatever is committed there must
    either score the checkpoint on data it demonstrably had not seen, or not
    score it at all — never the third thing, which is what was committed until
    T-05: a checkpoint score with nothing recorded about what it was scored on.
    """
    comparison = _load(COMPARISON)
    assert comparison["schema"] == 2, (
        "the committed comparison predates the leak check — re-run "
        "ml/evaluation/eval_backends.py"
    )
    checkpoint_scored = {"muril", "fused"} & set(comparison["results"])
    if comparison["status"] == "valid":
        assert comparison["leak_check"]["overlap_turns"] == 0
        assert checkpoint_scored == {"muril", "fused"}
    else:
        assert not checkpoint_scored, (
            f"status is {comparison['status']!r} but the checkpoint was scored "
            f"anyway: {sorted(checkpoint_scored)}"
        )
        assert comparison["reason"]


def test_recorded_scores_are_plausible():
    """A macro-F1 outside [0, 1] means something wrote garbage."""
    for backend, scores in _load(COMPARISON)["results"].items():
        assert 0.0 <= scores["macro_f1"] <= 1.0, backend
        assert 0.0 <= scores["weighted_f1"] <= 1.0, backend
