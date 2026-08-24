"""
Node policy — what gets retried, and what does not.

    .venv/bin/python -m pytest services/api/tests/test_orchestration_policy.py -q

ARCHITECTURE.md §2: "2 attempts, exponential backoff, only for
transient/network errors". The last clause is the one with teeth. Retrying a
`ValueError` from a malformed WHOIS response cannot succeed, and it spends a
frightened person's time twice to prove it.

One test here exists purely to pin a coupling: `policy.py` reads the exception
class name out of the string `agents/base.py` formatted into `AgentResult.error`.
That is a real dependency between two modules through a text format, and it is
the kind of thing that breaks silently, so it is asserted rather than assumed.
"""

from __future__ import annotations

import asyncio

import pytest

from schema.models import AgentResult, AgentStatus, InvestigationState, utc_now_iso
from services.api.agents.base import AgentContext, run_agent
from services.api.orchestration.policy import (
    DEFAULT_POLICY,
    POLICIES,
    NodePolicy,
    error_type_of,
    policy_for,
    should_retry,
)


def err(message: str) -> AgentResult:
    return AgentResult(agent="a", version="1.0.0", status=AgentStatus.ERROR, error=message)


class _Agent:
    name = "some_agent"
    version = "1.0.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        raise ConnectionResetError("the socket went away")


# --------------------------------------------------------------------------
# The budgets
# --------------------------------------------------------------------------


def test_the_defaults_match_the_architecture() -> None:
    assert DEFAULT_POLICY.timeout_s == 8.0
    assert DEFAULT_POLICY.attempts == 2


def test_the_documented_per_agent_budgets_are_the_ones_in_the_table() -> None:
    """ARCHITECTURE.md §2: "default 8 s; TI 3 s; APK 120 s async"."""
    assert POLICIES["threat_intel"].timeout_s == 3.0
    assert POLICIES["apk_static"].timeout_s == 120.0
    # Two minutes of decompilation produces the same answer the second time.
    assert POLICIES["apk_static"].attempts == 1


def test_an_unknown_agent_gets_the_default() -> None:
    assert policy_for(_Agent()) is DEFAULT_POLICY


def test_backoff_is_exponential_and_has_no_jitter() -> None:
    """No jitter, deliberately.

    Jitter desynchronises a thundering herd, which one investigation does not
    have, and it would make two runs of the same input differ — the exact
    property the Phase 9 ablations depend on not happening.
    """
    p = NodePolicy(backoff_s=0.25, backoff_factor=2.0, attempts=4)
    assert p.backoff_before(1) == 0.0
    assert p.backoff_before(2) == 0.25
    assert p.backoff_before(3) == 0.5
    assert p.backoff_before(4) == 1.0
    assert [p.backoff_before(i) for i in range(1, 5)] == [p.backoff_before(i) for i in range(1, 5)]


# --------------------------------------------------------------------------
# What is worth another attempt
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "ConnectionResetError: peer hung up",
        "OSError: [Errno 51] Network is unreachable",
        "TimeoutError: read timed out",
        "SSLError: handshake failed",
    ],
)
def test_transient_failures_are_retried(message: str) -> None:
    assert should_retry(err(message), "agent:a:error", 1, DEFAULT_POLICY)


@pytest.mark.parametrize(
    "message",
    [
        "ValueError: could not parse WHOIS response",
        "KeyError: 'registrar'",
        "AttributeError: NoneType has no attribute 'text'",
        "UnidentifiedImageError: truncated PNG",
        "ZeroDivisionError: division by zero",
    ],
)
def test_permanent_failures_are_not_retried(message: str) -> None:
    """A bug does not become less of a bug on the second call."""
    assert not should_retry(err(message), "agent:a:error", 1, DEFAULT_POLICY)


def test_a_timeout_is_retried_but_still_bounded() -> None:
    result = err("timed out after 8.0s")
    assert should_retry(result, "agent:a:timeout", 1, DEFAULT_POLICY)
    assert not should_retry(result, "agent:a:timeout", 2, DEFAULT_POLICY)


def test_a_cancelled_agent_is_not_retried() -> None:
    """Someone asked us to stop. Trying again ignores them."""
    assert not should_retry(err("cancelled before start"), "agent:a:cancelled", 1, DEFAULT_POLICY)


def test_a_degraded_result_is_not_retried() -> None:
    """DEGRADED is a *successful* answer from a fallback.

    Retrying it discards a usable answer hoping for a better one, on a path
    where the fallback exists precisely because the primary is unavailable.
    """
    degraded = AgentResult(agent="a", version="1.0.0", status=AgentStatus.DEGRADED)
    assert not should_retry(degraded, "agent:a:degraded", 1, DEFAULT_POLICY)


def test_an_ok_result_is_not_retried() -> None:
    ok = AgentResult(agent="a", version="1.0.0", status=AgentStatus.OK)
    assert not should_retry(ok, None, 1, DEFAULT_POLICY)


def test_the_attempt_budget_is_the_hard_stop() -> None:
    transient = err("ConnectionError: nope")
    assert should_retry(transient, "agent:a:error", 1, NodePolicy(attempts=2))
    assert not should_retry(transient, "agent:a:error", 2, NodePolicy(attempts=2))
    assert not should_retry(transient, "agent:a:error", 1, NodePolicy(attempts=1))


# --------------------------------------------------------------------------
# The coupling to agents/base.py, pinned
# --------------------------------------------------------------------------


def test_the_error_format_written_by_the_agent_harness_is_the_one_parsed_here() -> None:
    """`agents/base.py` formats "TypeName: message"; this reads that back.

    A dependency between two modules through a text format is exactly what
    breaks quietly, so it is asserted end to end rather than assumed: a real
    agent raises a real exception, the real harness formats it, and the parser
    recovers the class name.
    """
    state = InvestigationState(
        case_id="C", org_id="o", created_by="u", created_at=utc_now_iso()
    )
    result, tag = asyncio.run(
        run_agent(_Agent(), state, AgentContext(org_id="o", case_id="C", timeout_s=1.0))
    )

    assert result.status is AgentStatus.ERROR
    assert error_type_of(result) == "ConnectionResetError"
    assert should_retry(result, tag, 1, DEFAULT_POLICY), (
        "a genuine network failure from the real harness was classified as permanent"
    )


def test_an_unparseable_error_is_treated_as_permanent() -> None:
    """When in doubt, do not spend the attempt.

    A retry that cannot succeed costs a second timeout on a screen someone is
    waiting at; a missed retry costs one degraded answer. The asymmetry points
    one way.
    """
    assert error_type_of(err("something went wrong, no colon here")) is None
    assert not should_retry(err("something went wrong"), "agent:a:error", 1, DEFAULT_POLICY)


def test_a_result_with_no_error_has_no_error_type() -> None:
    assert error_type_of(AgentResult(agent="a", version="1.0.0", status=AgentStatus.OK)) is None
