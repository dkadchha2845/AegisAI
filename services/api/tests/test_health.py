"""
/api/health tells the truth about which model is serving.

The whole point of this endpoint, per the main.py docstring, is that "is the
good model loaded?" should be *a question with a checkable answer rather than a
hope*. It stopped being one: `loaded` was computed as `backend == "muril"`, so
once FusedStageClassifier started serving MuRIL's weights under the backend
name "fused", health reported `loaded: false` while the fine-tuned checkpoint
was demonstrably in memory and driving every prediction.

These tests pin the replacement predicate — `StageClassifier.checkpoint_backed`
— so a future backend cannot reintroduce the same class of lie. They are
written to be meaningful on both paths, because the two environments differ:
CI runs with no checkpoint on the runner (lexical fallback) and a developer
machine runs with one (fused). Anything asserted unconditionally therefore has
to hold for both.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.engine.classifier import (
    FusedStageClassifier,
    LexicalStageClassifier,
    MuRILStageClassifier,
    StageClassifier,
)
from services.api.main import app


class _FakeCheckpoint(StageClassifier):
    """Stands in for MuRIL so the predicate can be tested with no checkpoint.

    Instantiating the real MuRILStageClassifier requires the exported weights,
    which are absent on CI by design — that is the clean-clone path the suite
    asserts elsewhere.
    """

    backend = "muril"
    checkpoint_backed = True


# --- the predicate itself ---------------------------------------------------


def test_lexical_is_not_checkpoint_backed():
    assert LexicalStageClassifier().checkpoint_backed is False


def test_muril_class_declares_checkpoint_backed():
    # Asserted on the class, not an instance: constructing one needs the
    # weights, and this is the property that must survive a refactor.
    assert MuRILStageClassifier.checkpoint_backed is True


def test_fused_is_checkpoint_backed_when_a_component_is():
    fused = FusedStageClassifier(_FakeCheckpoint(), LexicalStageClassifier())
    assert fused.checkpoint_backed is True


def test_fused_reports_backed_when_checkpoint_is_the_secondary():
    # Ordering must not matter; load_classifier happens to pass MuRIL first.
    fused = FusedStageClassifier(LexicalStageClassifier(), _FakeCheckpoint())
    assert fused.checkpoint_backed is True


def test_fused_of_two_lexicals_is_not_checkpoint_backed():
    # The honest answer, and the reason this delegates instead of hard-coding
    # True for the fused backend.
    fused = FusedStageClassifier(LexicalStageClassifier(), LexicalStageClassifier())
    assert fused.checkpoint_backed is False


def test_backend_name_alone_no_longer_decides():
    """The regression, stated directly.

    A classifier whose backend is not the literal string "muril" can still be
    checkpoint-backed. This is the assertion the old implementation failed.
    """
    fused = FusedStageClassifier(_FakeCheckpoint(), LexicalStageClassifier())
    assert fused.backend != "muril"
    assert fused.checkpoint_backed is True


# --- what /api/health actually reports --------------------------------------


def _health() -> dict:
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200
    return r.json()["classifier"]


def test_health_loaded_matches_the_serving_classifier():
    """`loaded` is the serving classifier's own answer, on either path."""
    from services.api.engine.classifier import load_classifier

    clf = load_classifier()
    assert _health()["loaded"] is clf.checkpoint_backed


def test_health_is_self_consistent():
    """The fields must not contradict each other.

    Reporting backend "fused" alongside loaded false was the original defect,
    and it is the shape of contradiction worth pinning: any backend that fuses
    or wraps the checkpoint has the weights in memory.

    Caveat worth knowing: this test only *bites* where a checkpoint exists, so
    it passes vacuously on CI, where the lexical fallback is correct to report
    loaded false. The predicate tests above are the ones that hold everywhere —
    which is why the regression is pinned in both forms rather than just here.
    """
    clf = _health()
    if clf["backend"] == "lexical":
        assert clf["loaded"] is False
    else:
        # muril or fused — both mean the checkpoint is in memory.
        assert clf["loaded"] is True, (
            f"backend {clf['backend']!r} serves the checkpoint but health "
            f"reports loaded=False — {clf['reason']}"
        )


def test_health_lexical_fallback_is_flagged_degraded():
    """A genuine fallback is both not-loaded and reported as degraded.

    Guards the other direction: `loaded` must not be quietly forced True to
    make the endpoint look healthy.
    """
    body = TestClient(app).get("/api/health").json()
    if body["classifier"]["backend"] == "lexical" and not body["classifier"]["serving_best"]:
        assert body["classifier"]["loaded"] is False
        assert "clf:lexical_fallback" in body["degraded"]
