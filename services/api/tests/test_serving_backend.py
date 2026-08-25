"""
Which model a gate run proved — task 1.7b.

    .venv/bin/python -m pytest services/api/tests/test_serving_backend.py -q

Task 1.7 was ticked on 435 green tests that had never loaded the checkpoint the
application serves, because `ml/artifacts/` is gitignored and the worktree held
8 KB of it. 1.7a is the false positive that hid in that gap. CI is in the same
state permanently — no checkpoint step, so every gate run there is a fallback
run — and nothing in "439 passed" said so.

These tests do not close that gap; 4.9 owns getting a promoted checkpoint into
CI and 4.8 owns the false-positive harness that should run against it. What they
close is the third acceptance criterion: `serving_best` is now something a gate
asserts rather than a field on a dashboard that a human has to think to read.

The environment-dependent tests are written to bite in *both* directions —
each asserts the real state where it can and the invariant everywhere — so this
file is not itself another test that passes vacuously on the runner.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from services.api import serving
from services.api.config import settings
from services.api.main import app


@pytest.fixture(scope="module")
def report() -> dict:
    return serving.serving_report()


# --- the report and /api/health cannot disagree -----------------------------


def test_report_matches_health_field_for_field(report: dict) -> None:
    """One fact, two readers.

    `loaded` was reported wrongly twice by comparing `backend` to a string, and
    both times a second derivation was what made the two answers differ. This
    asserts the gate and the dashboard read the same three values, so a fix to
    one can never leave the other stale.
    """
    health = TestClient(app).get("/api/health").json()["classifier"]
    assert report["backend"] == health["backend"]
    assert report["loaded"] == health["loaded"]
    assert report["serving_best"] == health["serving_best"]
    assert report["reason"] == health["reason"]


def test_a_genuine_fallback_is_the_one_degraded_case(report: dict) -> None:
    """`serving_best` False and the degraded tag are the same condition.

    Lexical serving because it *won* the measured comparison is not a fallback
    and must not be tagged; lexical serving because nothing else exists must be.
    """
    health = TestClient(app).get("/api/health").json()
    tagged = "clf:lexical_fallback" in health["degraded"]
    assert tagged is (not report["serving_best"])


def test_checkpoint_present_but_not_loaded_is_never_reported_as_best(report: dict) -> None:
    """The silent-substitution case, asserted rather than assumed.

    A checkout with the 3.5 GB of weights but no torch installed serves the
    lexical model. That is legitimate — the requirements file calls torch
    optional — but it must never read as "the best model is serving", because
    that is exactly the state 1.7 was ticked in.
    """
    if report["checkpoint_present"] and not report["loaded"]:
        assert report["serving_best"] is False, report["reason"]


# --- the requirement -------------------------------------------------------


def test_the_default_requirement_is_met_by_any_backend(report: dict) -> None:
    """A clean clone must stay green. The default asks for nothing."""
    assert serving.unmet_requirements("any", report) == []


def test_this_run_meets_the_requirement_it_declared(report: dict) -> None:
    """The gate itself. This is the assertion `serving_best` was missing.

    With the setting unset it passes anywhere, which keeps CI and a clean clone
    green. With `AEGIS_REQUIRE_SERVING_BEST=1` it fails the *backend suite* — not
    a separate script somebody has to remember — the moment a fallback is
    serving. That is what makes `AEGIS_REQUIRE_SERVING_BEST=1 make gates` a gate
    run whose green means the model, and an ordinary `make gates` a gate run
    that says in its own output that it does not.
    """
    assert serving.unmet_requirements(report=report) == []


def test_requiring_the_best_model_fails_on_a_genuine_fallback() -> None:
    """`--require best` refuses a run that would prove the stand-in.

    Both directions are asserted against synthetic reports so this holds on a
    runner with no checkpoint and on a laptop with one.
    """
    fallback = {
        "backend": "lexical",
        "loaded": False,
        "serving_best": False,
        "reason": "no checkpoint exported",
        "checkpoint": "/nowhere/stage-classifier",
        "checkpoint_present": False,
    }
    problems = serving.unmet_requirements("best", fallback)
    assert len(problems) == 1
    # The message has to name the directory, or it sends a reader to the source
    # instead of to the empty folder that caused it.
    assert "/nowhere/stage-classifier" in problems[0]
    assert "no checkpoint" in problems[0]

    served = {**fallback, "backend": "fused", "loaded": True, "serving_best": True,
              "reason": "fused (muril + lexical): measured better", "checkpoint_present": True}
    assert serving.unmet_requirements("best", served) == []


def test_requiring_the_best_model_names_a_checkpoint_that_failed_to_load() -> None:
    """Present-but-unloadable and absent are different failures, said differently."""
    stalled = {
        "backend": "lexical",
        "loaded": False,
        "serving_best": False,
        "reason": "checkpoint failed to load: No module named 'torch'",
        "checkpoint": "/ml/artifacts/stage-classifier",
        "checkpoint_present": True,
    }
    (problem,) = serving.unmet_requirements("best", stalled)
    assert "present but did not load" in problem
    assert "torch" in problem


def test_requiring_a_fallback_fails_when_a_real_model_turns_up() -> None:
    """CI's declaration is a pin, not a preference.

    `--require fallback` is what the workflow runs, so the day a promoted
    checkpoint becomes reachable on the runner the step fails and someone has to
    decide what the gates require — rather than the suite quietly changing what
    it proves, which is how 1.7 happened.
    """
    served = {
        "backend": "fused", "loaded": True, "serving_best": True,
        "reason": "fused (muril + lexical): measured better (0.767 vs 0.375)",
        "checkpoint": "/ml/artifacts/stage-classifier", "checkpoint_present": True,
    }
    (problem,) = serving.unmet_requirements("fallback", served)
    assert "4.8 and 4.9" in problem
    assert serving.unmet_requirements("fallback", {**served, "serving_best": False}) == []


def test_the_setting_is_what_selects_the_default_requirement(monkeypatch) -> None:
    """`AEGIS_REQUIRE_SERVING_BEST=1 make gates` is the checkpoint-backed run.

    Asserted through the setting rather than by spawning a process, because the
    point is the wiring: `unmet_requirements()` with no argument must consult
    the setting, or the env var is a documented switch that does nothing.

    `Settings` is frozen, so the swap is a copy bound over the module's name
    rather than an attribute assignment — the immutability `test_config.py`
    asserts is the reason, and working around it in place would defeat it.
    """
    fallback = {
        "backend": "lexical", "loaded": False, "serving_best": False,
        "reason": "no checkpoint exported",
        "checkpoint": "/nowhere/stage-classifier", "checkpoint_present": False,
    }
    # Both settings are pinned rather than one being left ambient: this file is
    # meant to be run with AEGIS_REQUIRE_SERVING_BEST=1 as well as without, and
    # a test that reads the environment it is testing passes for the wrong
    # reason in one of the two runs.
    for required, expect_problems in ((False, False), (True, True)):
        monkeypatch.setattr(
            serving, "settings", settings.model_copy(update={"require_serving_best": required})
        )
        assert bool(serving.unmet_requirements(None, fallback)) is expect_problems


def test_an_unknown_requirement_is_refused() -> None:
    with pytest.raises(ValueError, match="requirement must be one of"):
        serving.unmet_requirements("mostly", {})


# --- what a run says about itself -------------------------------------------


def test_the_run_states_which_classifier_it_proved(report: dict) -> None:
    """The header and summary line name the backend and whether it is the best.

    This is the line that makes "439 passed" mean something specific. If it ever
    stops naming the backend, a fallback run and a checkpoint run look identical
    again.
    """
    line = serving.describe(report)
    assert report["backend"] in line
    assert report["reason"] in line
    if report["serving_best"]:
        assert "best available" in line
    else:
        assert "FALLBACK" in line


def test_the_cli_reports_and_honours_its_exit_code() -> None:
    """`python -m services.api.serving` is what CI runs, so it is run here.

    A subprocess rather than calling `main()`: the exit code and the module
    entry point are the contract the workflow depends on, and neither is
    exercised by importing the function.
    """
    base = [sys.executable, "-m", "services.api.serving"]
    ok = subprocess.run([*base, "--require", "any"], capture_output=True, text=True, timeout=300)
    assert ok.returncode == 0, ok.stderr
    assert "classifier:" in ok.stdout
    assert "checkpoint:" in ok.stdout

    # Whichever state this machine is in, exactly one of the two strict
    # requirements must fail — they are negations of each other.
    best = subprocess.run([*base, "--require", "best"], capture_output=True, text=True, timeout=300)
    fell = subprocess.run(
        [*base, "--require", "fallback"], capture_output=True, text=True, timeout=300
    )
    assert (best.returncode == 0) != (fell.returncode == 0), (best.stdout, fell.stdout)
    failed = best if best.returncode else fell
    assert "FAIL:" in failed.stderr
