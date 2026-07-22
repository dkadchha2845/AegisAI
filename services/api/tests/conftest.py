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
os.environ["PRESAGE_LLM"] = "none"
