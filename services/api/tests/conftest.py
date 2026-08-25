"""
Test isolation from the developer's .env.

The running demo server reads `.env` for convenience — a persistent
`DATABASE_URL`, a Gemini key for live explanations. The test suite must not:
tests have to be hermetic, offline, and independent of whatever a developer
happens to have configured locally. A persistent DB in `.env` would otherwise
carry state between test runs (seed collisions, stale users), and a live LLM
key would put a network call in the middle of a unit test.

So we pin the two capabilities that `.env` can switch on to their safe,
offline defaults *before* `services.api.config` is first imported. Setting the
keys in `os.environ` here means the minimal .env loader in `config.py` treats
them as already-present real environment variables and leaves them alone
(real env always wins), which forces:

  * an ephemeral, per-process SQLite temp file (the zero-setup default), and
  * the templated explainer (no LLM backend), so nothing reaches the network.

Individual tests that need enforcement or a specific backend still flip their
own env and reload, exactly as before.
"""

from __future__ import annotations

import os

# Empty string, not `del`: config.py reads `os.getenv("DATABASE_URL") or None`,
# so "" collapses to the ephemeral default, and the key being present blocks the
# .env loader from overriding it.
os.environ["DATABASE_URL"] = ""
os.environ["AEGIS_LLM"] = "none"

# Task 1.8's queue is pinned off for the same reason. A developer's machine may
# well have the compose stack up, and with a reachable broker every submission
# would be handed to a Celery worker that the test session has not started —
# so the suite would hang on a stream waiting for a node nobody is executing.
# Worse, it would hang *only* on machines with Redis running, which is the kind
# of "green here, red there" the two lines above already exist to prevent.
#
# The queue path is not therefore untested: `test_jobs_*.py` turn it back on
# explicitly and skip with a printed reason when no broker answers. See the
# summary line this file writes, and task 1.7b for why it is printed.
os.environ["AEGIS_QUEUE"] = "0"


# ---------------------------------------------------------------------------
# The built-in agent set, restored before every test
# ---------------------------------------------------------------------------

import pytest


@pytest.fixture(autouse=True)
def _builtin_agents():
    """Every test starts with the process's real agent set registered.

    `registry.clear()` is module-global state, and three test modules call it —
    `test_agent_registry`, `test_input_classifier` and `test_orchestration_graph`
    all need to start from empty. The registry's own docstring names the hazard
    that creates: "the suite passes or fails depending on file order".

    It was not hypothetical. Task 1.7 registered seven engine adapters, and the
    1.6 API tests went on passing in a full run while failing when run alone —
    because a module earlier in the alphabet had cleared the registry, so the
    lifecycle tests were exercising an agent set of one. A suite that is green
    for that reason is not green.

    Restoring in setup rather than teardown is what makes it robust: a module
    that wants an empty registry clears it in its own fixture, which runs after
    this one, so both intents are satisfied without either knowing about the
    other.
    """
    from services.api import agents as agents_pkg
    from services.api.agents import registry

    for name in agents_pkg.__all__:
        cls = getattr(agents_pkg, name)
        if getattr(cls, "name", None) not in registry.names():
            registry.register(cls)
    yield


# ---------------------------------------------------------------------------
# What this run proves (task 1.7b)
# ---------------------------------------------------------------------------


def pytest_report_header() -> str:
    """Name the serving classifier at the top of every run.

    Task 1.7 was ticked on a green suite that had never loaded the model the
    application serves, and 1.7a is the defect that hid there. Nothing in the
    output distinguished the two runs: "435 passed" reads the same either way.
    It does not any more — a run states which classifier it proved before it
    proves anything, so a tick earned against the lexical stand-in is visible in
    the evidence rather than inferable from the size of `ml/artifacts/`.

    Importing inside the function, not at module scope: this file runs before
    any test collects, and loading the classifier at import time would make a
    2 GB torch import a precondition of `pytest --collect-only`.
    """
    from services.api.serving import describe

    return "\n".join([describe(), _queue_line()])


def pytest_terminal_summary(terminalreporter) -> None:  # type: ignore[no-untyped-def]
    """The same line again, at the end of the run.

    Not redundant with the header. `addopts = "-q"` in pyproject.toml combines
    with the explicit `-q` in `make test` to give verbosity -2, at which pytest
    prints neither the header *nor* its own "N passed" line — so a gate run's
    entire output is a row of dots. This hook writes below that threshold, which
    makes the serving backend the one thing a `make gates` run always states
    about itself.
    """
    from services.api.serving import describe

    terminalreporter.write_line(describe())
    terminalreporter.write_line(_queue_line())


def _queue_line() -> str:
    """Whether the Redis-backed half of task 1.8 was exercised or skipped.

    The queue is pinned off for the suite (see the top of this file), so the
    only thing that decides whether `test_jobs_journal.py` and
    `test_jobs_worker.py` actually run is whether a broker answers. That makes
    them exactly the shape 1.7b is about — tests that can pass by not running —
    so the run says which it did.
    """
    from services.api.jobs import broker

    ok, reason = broker.probe()
    where = broker.describe()
    if ok:
        return f"queue: broker at {where} answered — Redis journal and worker tests ran"
    return f"queue: no broker at {where} ({reason.split(':')[0]}) — those tests SKIPPED"
