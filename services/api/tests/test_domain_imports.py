"""
The shared domain package is really imported, not silently falling back.

`packages/aegis_core` holds the single source of truth for the eight scam
stages and their threat weights. Two places in the API import it behind a
`try/except ImportError` with a hardcoded fallback, so that an image built
without the package still starts.

That fallback is a trap worth testing against. It defines the *same eight
label strings* but an **empty** `BY_LABEL`, which is where the threat weights
live. So if the import breaks, nothing raises, no existing test fails, the
stage classifier keeps returning plausible labels — and threat scoring quietly
loses its weighting. The failure is invisible precisely because the part that
is easy to check (the label list) is identical.

These tests assert the real package is the one in use. They are the reason it
was safe to move the package out of `ml/` and onto an installed distribution.
"""

from __future__ import annotations

import pytest


def test_aegis_core_is_installed():
    """The package resolves at all, and from packages/, not from ml/."""
    import aegis_core

    assert aegis_core.__file__ is not None
    assert "packages/aegis_core" in aegis_core.__file__.replace("\\", "/"), (
        f"aegis_core resolved from an unexpected location: {aegis_core.__file__}"
    )


def test_taxonomy_import_is_live():
    """`BY_LABEL` is populated — i.e. the fallback is NOT what is serving.

    The fallback sets `BY_LABEL = {}`. An empty mapping here means threat
    weighting is silently gone, which is the exact failure this guards.
    """
    from services.api.engine.classifier import BY_LABEL, LABELS

    assert len(LABELS) == 8
    assert len(BY_LABEL) == 8, (
        "BY_LABEL is empty — the hardcoded ImportError fallback is in use and "
        "stage threat weights have been silently lost. Check that aegis-core "
        "is installed (pip install -e packages/aegis_core)."
    )


def test_taxonomy_labels_match_the_package():
    """The API's labels are the package's labels, not a drifted copy."""
    from aegis_core.taxonomy import LABELS as PACKAGE_LABELS

    from services.api.engine.classifier import LABELS as SERVED_LABELS

    assert list(SERVED_LABELS) == list(PACKAGE_LABELS)


def test_stage_threat_weights_are_present():
    """Every stage carries a usable weight, which is what BY_LABEL is for.

    This is the payload the fallback loses: with `BY_LABEL = {}` there are no
    stages to weight, and `classifier.py` silently reads `.get(label) -> None`.
    """
    from services.api.engine.classifier import BY_LABEL

    for label, stage in BY_LABEL.items():
        assert hasattr(stage, "threat_weight"), f"{label} carries no threat_weight"
        assert 0.0 <= stage.threat_weight <= 1.0, (
            f"{label} threat_weight {stage.threat_weight} outside 0-1"
        )

    # The arc's escalation must be real, not incidentally ordered.
    assert BY_LABEL["PAYMENT_EXECUTION"].threat_weight > BY_LABEL["GREETING"].threat_weight
    assert BY_LABEL["BENIGN"].threat_weight == 0.0


def test_hinglish_markers_are_the_real_set():
    """Language detection uses the validated marker set, not the stub.

    The inline fallback in `ingest/language.py` lists 19 markers; the package
    carries far more. Counting distinguishes them without hardcoding a total
    that would break every time the corpus grows.
    """
    from aegis_core.hinglish import HINDI_MARKERS as PACKAGE_MARKERS

    from services.api.ingest.language import HINDI_MARKERS as SERVED_MARKERS

    assert SERVED_MARKERS is PACKAGE_MARKERS or set(SERVED_MARKERS) == set(PACKAGE_MARKERS)
    assert len(SERVED_MARKERS) > 19, (
        "language.py appears to be using its inline fallback marker stub"
    )


@pytest.mark.parametrize(
    "module",
    ["taxonomy", "schema", "seeds", "entities", "hinglish", "llm"],
)
def test_every_domain_module_imports(module):
    """The whole package is importable, so the corpus pipeline still runs.

    `ml/` scripts import these directly; a partial move would break dataset
    generation without touching a single API test.
    """
    __import__(f"aegis_core.{module}")
