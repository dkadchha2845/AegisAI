"""
The agent execution policy — ARCHITECTURE.md §2, made checkable.

    .venv/bin/python -m pytest services/api/tests/test_agent_base.py -q

The acceptance criterion that matters for 1.2 is the third one: *a raising agent
yields `status="error"` without propagating*. Everything else in this file exists
because the ways an agent can fail are more varied than "it raised", and each of
them has to end at the same place — one valid `AgentResult`, an investigation
that still completes, and a `degraded` tag that says what was lost.

The agents here are toys on purpose. A real agent's behaviour is its own test's
problem; what is under test is the harness that has to survive agents nobody has
written yet.

Async tests go through `asyncio.run()` rather than pytest-asyncio. One dependency
and one config key avoided, a fresh event loop per test for free, and nothing
about these assertions needs a shared loop. If the orchestrator tests in 1.3 turn
out to need loop-scoped fixtures, that is the moment to add the plugin — not now,
on the strength of a decorator.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from schema.models import (
    AgentResult,
    AgentStatus,
    Finding,
    InputType,
    InvestigationState,
    utc_now_iso,
)
from services.api.agents.base import (
    DEFAULT_TIMEOUT_S,
    STAGE_ORDER,
    Agent,
    AgentContext,
    Stage,
    run_agent,
    stage_of,
)


def make_state(**kw: object) -> InvestigationState:
    return InvestigationState(
        case_id="AGIS-TEST-1",
        org_id="aegis",
        created_by="test@aegis.local",
        created_at=utc_now_iso(),
        **kw,  # type: ignore[arg-type]
    )


def make_ctx(**kw: object) -> AgentContext:
    return AgentContext(org_id="aegis", case_id="AGIS-TEST-1", **kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The toys
# --------------------------------------------------------------------------


class GoodAgent:
    name = "good"
    version = "1.0.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.OK,
            confidence=0.9,
            findings=[Finding(label="toy", value="1", source="test")],
            features={"toy": 1.0},
            provenance=["test"],
        )


class RaisingAgent:
    name = "raiser"
    version = "1.0.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        raise RuntimeError("whois socket exploded")


class HangingAgent:
    name = "hanger"
    version = "1.0.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        await asyncio.sleep(30)
        raise AssertionError("unreachable: the harness should have cut this off")


class NotApplicableAgent:
    name = "apk_toy"
    version = "1.0.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return InputType.APK in state.input_types

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        raise AssertionError("unreachable: can_handle() said no")


class DegradingAgent:
    """Answered — but from a cached snapshot. The status only it can know."""

    name = "degrader"
    version = "1.0.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.DEGRADED,
            confidence=0.4,
            provenance=["urlhaus:snapshot"],
        )


class LiarAgent:
    """Returns the wrong type. Someone will eventually write this by accident."""

    name = "liar"
    version = "1.0.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        return {"status": "ok"}  # type: ignore[return-value]


class SlowButFineAgent:
    name = "slow"
    version = "1.0.0"

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        await asyncio.sleep(0.05)
        return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)


# --------------------------------------------------------------------------
# The protocol itself
# --------------------------------------------------------------------------


def test_a_plain_class_satisfies_the_protocol() -> None:
    """No base class, no registration, no mixin — just the right shape.

    This is what lets 1.7 wrap the inherited engine in adapters without the
    engine growing a dependency on the agent layer.
    """
    assert isinstance(GoodAgent(), Agent)


def test_a_class_missing_run_does_not_satisfy_it() -> None:
    class Incomplete:
        name = "incomplete"
        version = "1.0.0"

        def can_handle(self, state: InvestigationState) -> bool:
            return True

    assert not isinstance(Incomplete(), Agent)


# --------------------------------------------------------------------------
# The four outcomes
# --------------------------------------------------------------------------


def test_a_working_agent_returns_its_result_untouched() -> None:
    result, tag = asyncio.run(run_agent(GoodAgent(), make_state(), make_ctx()))
    assert result.status is AgentStatus.OK
    assert result.agent == "good" and result.version == "1.0.0"
    assert result.features == {"toy": 1.0}
    assert tag is None


def test_a_raising_agent_yields_error_and_does_not_propagate() -> None:
    """The acceptance criterion for 1.2.

    An investigation that dies because one agent threw is the exact opposite of
    the degradation invariant — and the citizen waiting on it gets nothing at
    all rather than a partial answer.
    """
    result, tag = asyncio.run(run_agent(RaisingAgent(), make_state(), make_ctx()))

    assert result.status is AgentStatus.ERROR
    assert result.error is not None
    assert "RuntimeError" in result.error and "whois socket exploded" in result.error
    assert result.confidence == 0.0
    assert result.findings == []
    assert tag == "agent:raiser:error"


def test_a_hanging_agent_is_cut_off_at_its_timeout() -> None:
    started = time.monotonic()
    result, tag = asyncio.run(run_agent(HangingAgent(), make_state(), make_ctx(timeout_s=0.1)))
    took = time.monotonic() - started

    assert result.status is AgentStatus.ERROR
    assert "timed out" in (result.error or "")
    assert tag == "agent:hanger:timeout"
    # The point of a timeout is the wall clock, so assert on it.
    assert took < 2.0, f"the 30s sleep was not cut off; took {took:.1f}s"


def test_an_inapplicable_agent_is_skipped_not_run() -> None:
    state = make_state(input_types=[InputType.TEXT])
    result, tag = asyncio.run(run_agent(NotApplicableAgent(), state, make_ctx()))

    assert result.status is AgentStatus.SKIPPED
    assert result.latency_ms == 0
    # Not applying is not a shortfall — tagging it would cry wolf on every
    # investigation, and a `degraded` field people learn to ignore is worthless.
    assert tag is None


def test_the_same_agent_runs_when_the_input_type_matches() -> None:
    state = make_state(input_types=[InputType.APK])
    with pytest.raises(AssertionError, match="unreachable"):
        # Proves can_handle() is what gated it, not some other accident.
        asyncio.run(NotApplicableAgent().run(state, make_ctx()))
    assert NotApplicableAgent().can_handle(state)


# --------------------------------------------------------------------------
# Degraded is the agent's word, not the harness's
# --------------------------------------------------------------------------


def test_a_self_declared_degraded_result_is_tagged() -> None:
    result, tag = asyncio.run(run_agent(DegradingAgent(), make_state(), make_ctx()))
    assert result.status is AgentStatus.DEGRADED
    assert tag == "agent:degrader:degraded"
    assert result.provenance == ["urlhaus:snapshot"]


def test_error_and_degraded_stay_distinguishable() -> None:
    """A failure is not a fallback.

    Only the agent knows it answered from a cache. Collapsing "I could not
    answer" into "I answered with a caveat" would leave 4.1 unable to tell how
    much weight a result deserves.
    """
    err, _ = asyncio.run(run_agent(RaisingAgent(), make_state(), make_ctx()))
    deg, _ = asyncio.run(run_agent(DegradingAgent(), make_state(), make_ctx()))
    assert err.status is not deg.status


# --------------------------------------------------------------------------
# Latency is measured, not asserted
# --------------------------------------------------------------------------


def test_latency_is_recorded_even_when_the_agent_forgets() -> None:
    result, _ = asyncio.run(run_agent(SlowButFineAgent(), make_state(), make_ctx()))
    assert result.status is AgentStatus.OK
    assert result.latency_ms >= 40, "the harness should have filled in the real elapsed time"


def test_a_timeout_records_the_time_it_actually_burned() -> None:
    """A timeout logging 0 ms would flatter the p95 in 9.4.

    "No claim without a measurement" cuts both ways: the failures have to be in
    the latency distribution too, or the number is a selective average.
    """
    result, _ = asyncio.run(run_agent(HangingAgent(), make_state(), make_ctx(timeout_s=0.15)))
    assert result.latency_ms >= 100


def test_an_agent_returning_the_wrong_type_is_contained() -> None:
    result, tag = asyncio.run(run_agent(LiarAgent(), make_state(), make_ctx()))
    assert result.status is AgentStatus.ERROR
    assert "expected AgentResult" in (result.error or "")
    assert tag == "agent:liar:error"


# --------------------------------------------------------------------------
# Cancellation and deadlines
# --------------------------------------------------------------------------


def test_a_cancelled_context_stops_work_before_it_starts() -> None:
    ctx = make_ctx()
    ctx.cancel.set()
    result, tag = asyncio.run(run_agent(HangingAgent(), make_state(), ctx))
    assert result.status is AgentStatus.ERROR
    assert tag == "agent:hanger:cancelled"


def test_a_deadline_beats_a_generous_per_agent_timeout() -> None:
    """An agent allowed 8 s cannot have 8 s when the investigation has 0.1 s left.

    This is what stops a nested sub-investigation at depth 2 from starting a
    fresh full budget and blowing the parent's latency target.
    """
    ctx = make_ctx(timeout_s=8.0, deadline=time.monotonic() + 0.1)
    started = time.monotonic()
    result, tag = asyncio.run(run_agent(HangingAgent(), make_state(), ctx))
    assert result.status is AgentStatus.ERROR and tag == "agent:hanger:timeout"
    assert time.monotonic() - started < 2.0


def test_remaining_falls_to_zero_and_never_negative() -> None:
    ctx = make_ctx(deadline=time.monotonic() - 5)
    assert ctx.remaining_s() == 0.0


def test_a_child_context_inherits_the_deadline_and_shares_cancellation() -> None:
    parent = make_ctx(timeout_s=8.0, deadline=time.monotonic() + 3)
    child = parent.child(timeout_s=3.0)

    assert child.depth == parent.depth + 1
    assert child.deadline == parent.deadline, "a child must not start a fresh budget"
    assert child.max_depth == parent.max_depth
    assert child.cancel is parent.cancel

    parent.cancel.set()
    assert child.cancel.is_set(), "cancelling the parent must cancel what it spawned"


def test_the_default_timeout_matches_the_architecture() -> None:
    assert DEFAULT_TIMEOUT_S == 8.0


# --------------------------------------------------------------------------
# The benign case — the harness must not invent anything
# --------------------------------------------------------------------------


def test_the_harness_adds_no_findings_of_its_own() -> None:
    """The false-positive test for this layer.

    Every agent ships one; the harness needs one too, for a subtler reason. If
    `run_agent` ever synthesised a finding — a "capability unavailable" note
    promoted into evidence, say — it would appear on every investigation
    including the benign ones, and a benign message would acquire an accusation
    from plumbing rather than from anything a scammer did.
    """

    class QuietAgent:
        name = "quiet"
        version = "1.0.0"

        def can_handle(self, state: InvestigationState) -> bool:
            return True

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    benign = make_state(input_types=[InputType.TEXT])
    for agent in (QuietAgent(), RaisingAgent(), HangingAgent(), NotApplicableAgent()):
        result, _ = asyncio.run(run_agent(agent, benign, make_ctx(timeout_s=0.1)))
        assert result.findings == [], f"{agent.name} route invented a finding"
        assert result.features == {}, f"{agent.name} route invented a feature"
        assert result.confidence == 0.0 or result.status is AgentStatus.OK


def test_remaining_falls_back_to_the_plain_timeout_without_a_deadline() -> None:
    assert make_ctx(timeout_s=4.0).remaining_s() == 4.0


def test_cancellation_propagates_rather_than_being_swallowed() -> None:
    """`CancelledError` is the one exception allowed past the harness.

    If it were caught and turned into an ERROR result, the task would report
    completion instead of dying, `asyncio.gather` could never shut a fan-out
    down, and cancelling an investigation would hang until every agent's timeout
    expired. Containing agent failures must not mean containing the event loop's
    own control flow.
    """

    class CooperativeAgent:
        name = "cooperative"
        version = "1.0.0"

        def can_handle(self, state: InvestigationState) -> bool:
            return True

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            await asyncio.sleep(5)
            raise AssertionError("unreachable")

    async def scenario() -> str:
        task = asyncio.create_task(
            run_agent(CooperativeAgent(), make_state(), make_ctx(timeout_s=5.0))
        )
        await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled"
        return "swallowed"

    assert asyncio.run(scenario()) == "cancelled"


def test_a_parallel_fan_out_completes_even_when_one_agent_explodes() -> None:
    """The property the whole task exists for, in the shape 1.3 will use it.

    Three agents run concurrently. One returns cleanly, one raises, one hangs
    past its timeout. The investigation gets three results and two degraded
    tags — not an exception, and not two results and a traceback.
    """

    async def scenario() -> tuple[list[AgentResult], list[str]]:
        state, ctx = make_state(), make_ctx(timeout_s=0.15)
        pairs = await asyncio.gather(
            *(
                run_agent(a, state, ctx)
                for a in (GoodAgent(), RaisingAgent(), HangingAgent())
            )
        )
        return [r for r, _ in pairs], [t for _, t in pairs if t]

    results, tags = asyncio.run(scenario())

    assert len(results) == 3
    assert all(isinstance(r, AgentResult) for r in results)
    assert {r.agent: r.status for r in results} == {
        "good": AgentStatus.OK,
        "raiser": AgentStatus.ERROR,
        "hanger": AgentStatus.ERROR,
    }
    assert sorted(tags) == ["agent:hanger:timeout", "agent:raiser:error"]
    # The one agent that worked still contributed its evidence.
    good = next(r for r in results if r.agent == "good")
    assert good.findings and good.features == {"toy": 1.0}


# --------------------------------------------------------------------------
# Tiers — what gives the investigation graph its shape
# --------------------------------------------------------------------------


def test_an_agent_without_a_declared_tier_lands_in_investigate() -> None:
    """The default has to be the useful one.

    Most agents investigate. Making the tier a required declaration would force
    a decision at the moment the answer is almost always "the middle one", and
    would stop 1.7's adapters from being four lines long.
    """
    assert stage_of(GoodAgent()) is Stage.INVESTIGATE


def test_a_declared_tier_is_honoured_as_an_enum_or_as_its_string() -> None:
    """A plain string is accepted so an adapter need not import this module."""

    class Enumerated:
        name = "enumerated"
        version = "1.0.0"
        stage = Stage.JUDGE

    class Stringly:
        name = "stringly"
        version = "1.0.0"
        stage = "extract"

    assert stage_of(Enumerated()) is Stage.JUDGE  # type: ignore[arg-type]
    assert stage_of(Stringly()) is Stage.EXTRACT  # type: ignore[arg-type]


def test_a_nonsense_tier_is_coerced_rather_than_raised_on() -> None:
    """The registry validates at import time; an investigation in flight is the
    wrong place to discover a typo, and dropping the agent entirely would be a
    silent capability loss."""

    class Typo:
        name = "typo"
        version = "1.0.0"
        stage = "investigat"

    class Wrong:
        name = "wrong"
        version = "1.0.0"
        stage = 3

    assert stage_of(Typo()) is Stage.INVESTIGATE  # type: ignore[arg-type]
    assert stage_of(Wrong()) is Stage.INVESTIGATE  # type: ignore[arg-type]


def test_the_tier_order_is_explicit_not_declaration_order() -> None:
    """`STAGE_ORDER` is a tuple, not `list(Stage)`.

    Execution order is behaviour. Deriving it from the order enum members happen
    to be declared in would make a harmless-looking reorder a silent change to
    what runs when.
    """
    assert STAGE_ORDER == (Stage.EXTRACT, Stage.INVESTIGATE, Stage.REASON, Stage.JUDGE)
    assert set(STAGE_ORDER) == set(Stage)


def test_the_agent_tier_is_not_the_scam_arc_stage() -> None:
    """Two different ideas that want the same English word.

    `agents.base.Stage` is where an agent sits in the graph;
    `schema.models.Stage` is the scam arc (GREETING, FEAR_INDUCTION, ...).
    Confusing them would be easy and expensive, so the distinction is asserted.
    """
    from schema.models import Stage as ScamStage

    assert Stage is not ScamStage
    assert {s.value for s in Stage}.isdisjoint({s.value for s in ScamStage})
