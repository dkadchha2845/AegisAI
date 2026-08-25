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
