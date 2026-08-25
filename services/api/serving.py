"""
Which classifier a run actually proved — task 1.7b.

**Why it exists.** Task 1.7 was ticked on 435 green tests that had never seen
the model the application serves. `ml/artifacts/` is gitignored, so the worktree
held 8 KB where a full checkout holds 3.5 GB, and every test therefore exercised
the lexical fallback. 1.7a is the defect that hid there: a benign delivery notice
printed "Stage: Verification Demand", and the suite was green throughout. The
same is permanently true of CI, which has no checkpoint step at all.

The gap is not that the fallback runs. It is that **a green run does not say
which model it proved**, so "439 passed" reads identically whether it exercised
the served model or a stand-in for it. That is the part fixable without the
model registry, and it is what this module fixes: the facts `/api/health`
already reports are turned into something a gate asserts and a test run prints,
rather than something a human notices on a dashboard if they think to look.

**What it consumes.** `engine/classifier.py`'s selection state — the same three
module globals `/api/health` reads — plus the checkpoint path from settings.

**What it outputs.** `serving_report()`, a dict of checked facts;
`describe()`, one line for a test-run header; and `unmet_requirements()`, the
reasons this run does not meet the requirement it was asked to meet.

**How it connects.** `tests/conftest.py` prints `describe()` as a pytest report
header, so every `make gates` run states what it proved. `test_serving_backend.py`
asserts the requirement. `python -m services.api.serving --require fallback` is
the CI step that pins the runner's known state. `/api/health` is unchanged and
remains the same three facts read by a different consumer.

**How it is evaluated.** `tests/test_serving_backend.py`: the report agrees with
`/api/health` field for field, the requirement passes on a served checkpoint and
fails on a genuine fallback, and the header names the backend.

**Limitations, stated.** This makes the gap *visible*; it does not close it. The
two acceptance criteria that do — a promoted checkpoint obtainable in CI (4.9),
and the false-positive harness running against a served model (4.8) — are owned
by the tasks that own the model registry and the harness. Until then the honest
description of a green CI run is "the fallback passed", and that sentence is now
printed by the run itself.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List, Optional

from .config import settings
from .engine import classifier as classifier_mod

#: The three things `--require` can ask of a run.
#:
#: `best` is "the best available model is serving" — either the promoted
#: checkpoint, or the lexical model *because it won the measured comparison*.
#: `fallback` is its negation and exists for one reason: CI's state is known and
#: permanent, so asserting it turns "no checkpoint here" from an unstated
#: condition into a checked one. The day 4.9 puts a promoted checkpoint on the
#: runner, that step fails and somebody has to decide what the gates require,
#: instead of the suite quietly changing what it proves.
REQUIREMENTS = ("any", "best", "fallback")


def serving_report() -> Dict[str, Any]:
    """The checked facts about what is serving, loading the classifier if needed.

    Deliberately the same fields `/api/health` publishes, read from the same
    module globals rather than recomputed. A second derivation of "is the good
    model serving" is a second thing that can be right while the first is wrong,
    which is the class of bug `loaded` was already fixed for twice.
    """
    classifier = classifier_mod.load_classifier()
    checkpoint_dir = settings.classifier_dir
    return {
        "backend": classifier.backend,
        "loaded": classifier.checkpoint_backed,
        "serving_best": not classifier_mod.serving_is_fallback,
        "reason": classifier_mod.selection_reason,
        "checkpoint": str(checkpoint_dir),
        # Present-on-disk is tracked separately from loaded, because the two
        # disagreeing is itself the interesting state: a checkout that has the
        # 3.5 GB of weights but no torch installed serves the fallback, and that
        # is precisely the silent substitution worth failing a checkpoint-backed
        # gate run over.
        "checkpoint_present": checkpoint_dir.exists() and (checkpoint_dir / "config.json").exists(),
    }


def describe(report: Optional[Dict[str, Any]] = None) -> str:
    """One line naming what this run proves. Printed by the pytest header."""
    r = report if report is not None else serving_report()
    quality = "best available" if r["serving_best"] else "FALLBACK — not what the app serves"
    return f"classifier: {r['backend']} ({quality}) — {r['reason']}"


def unmet_requirements(
    requirement: Optional[str] = None, report: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Why this run does not meet `requirement`. Empty means it does.

    A list rather than a bool so the failure names the checkpoint path and the
    selection reason: "serving_best is False" sends a reader to the source,
    "no checkpoint exported at ml/artifacts/stage-classifier" sends them to the
    directory that is empty.

    `requirement` defaults to the `AEGIS_REQUIRE_SERVING_BEST` setting, so a
    developer with the weights runs the ordinary gates with the model made
    mandatory and finds out immediately when it is not there — rather than three
    tasks later, from a benign message naming a scam stage.
    """
    if requirement is None:
        requirement = "best" if settings.require_serving_best else "any"
    if requirement not in REQUIREMENTS:
        raise ValueError(f"requirement must be one of {REQUIREMENTS}, not {requirement!r}")

    r = report if report is not None else serving_report()
    if requirement == "any":
        return []

    if requirement == "best":
        if r["serving_best"]:
            return []
        detail = (
            f"the checkpoint at {r['checkpoint']} is present but did not load"
            if r["checkpoint_present"]
            else f"no checkpoint at {r['checkpoint']}"
        )
        return [
            f"a genuine fallback is serving ({r['backend']}) — {detail}. "
            f"Selection said: {r['reason']}. This run proves the fallback, not "
            f"the model the application serves."
        ]

    # requirement == "fallback"
    if not r["serving_best"]:
        return []
    return [
        f"{r['backend']} is serving as the best available model ({r['reason']}), "
        f"but this run was declared to be a fallback run. If a promoted "
        f"checkpoint is now reachable here, decide what the gates require "
        f"(tasks 4.8 and 4.9) rather than leaving the declaration stale."
    ]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m services.api.serving",
        description="Report which classifier is serving, and optionally require one.",
    )
    parser.add_argument(
        "--require",
        choices=REQUIREMENTS,
        default=None,
        help="exit non-zero unless this holds; default comes from "
             "AEGIS_REQUIRE_SERVING_BEST ('best' when set, otherwise 'any')",
    )
    args = parser.parse_args(argv)

    report = serving_report()
    print(describe(report))
    for key in ("checkpoint", "checkpoint_present", "loaded", "serving_best"):
        print(f"  {key}: {report[key]}")

    problems = unmet_requirements(args.require, report)
    for problem in problems:
        print(f"\nFAIL: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())


__all__ = ["REQUIREMENTS", "describe", "main", "serving_report", "unmet_requirements"]
