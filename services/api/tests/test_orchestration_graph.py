"""
The investigation graph — task 1.3's four acceptance criteria, and the edges
around them.

    .venv/bin/python -m pytest services/api/tests/test_orchestration_graph.py -q

    1. the graph compiles and renders to Mermaid via a CLI
    2. one node deliberately times out and the investigation still completes,
       with `degraded` populated
    3. the trace shows per-node latency
    4. same input + fixed seeds ⇒ same output

(4) is the one the paper rests on, and it has a subtlety worth stating: two runs
are never byte-identical, because an investigation records how long it took. So
the claim is made precise by `determinism.fingerprint()`, which hashes
everything except the timings — and the test below deliberately uses agents with
*randomised* latency, so a fingerprint that survives them is saying something.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Dict, Iterator, List

import pytest

from schema.models import (
    AgentResult,
    AgentStatus,
    EvidenceItem,
    Finding,
    InputType,
    InvestigationState,
    InvestigationStatus,
    utc_now_iso,
)
from services.api.agents import registry
from services.api.agents.base import AgentContext, Stage
from services.api.orchestration import graph as orch
from services.api.orchestration.determinism import diff_summary, fingerprint


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    registry.clear()
    yield
    registry.clear()


def make_state(**kw: Any) -> InvestigationState:
    return InvestigationState(
        case_id="AGIS-GRAPH-1",
        org_id="aegis",
        created_by="test@aegis.local",
        created_at=utc_now_iso(),
        input_types=[InputType.TEXT],
        inputs=[EvidenceItem(id="ev-1", kind=InputType.TEXT, text="pay verify@ybl now")],
        **kw,
    )


def run(state: InvestigationState, **kw: Any) -> InvestigationState:
    return asyncio.run(orch.investigate(state, **kw))


# --------------------------------------------------------------------------
# The toys
# --------------------------------------------------------------------------


class _Ok:
    """Base for a well-behaved agent in a given tier."""

    name = "override"
    version = "1.0.0"
    stage = Stage.INVESTIGATE

    def can_handle(self, state: InvestigationState) -> bool:
        return True

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.OK,
            confidence=0.5,
            findings=[Finding(label="seen", value=self.name, source="toy")],
            features={f"{self.name}_ran": 1.0},
        )


def register_ok(agent_name: str, stage: Stage = Stage.INVESTIGATE) -> None:
    registry.register(type("Ok", (_Ok,), {"name": agent_name, "stage": stage}))


# --------------------------------------------------------------------------
# 1 — compiles and renders
# --------------------------------------------------------------------------


def test_the_graph_compiles_with_an_empty_registry() -> None:
    """A clean clone with no agents imported still builds a graph.

    Same reason the API boots with no compose stack: the skeleton is not
    conditional on its contents, and a build that fails without agents would
    make `--summary` useless for the exact question it answers.
    """
    assert orch.build_graph() is not None


def test_it_renders_to_mermaid_with_every_tier() -> None:
    diagram = orch.render_mermaid()
    assert "graph TD" in diagram
    for node in ("begin", "extract_stage", "investigate_stage", "reason_stage", "judge_stage", "finish"):
        assert node in diagram, f"{node} missing from the diagram"


def test_the_cli_prints_the_diagram_and_the_summary(capsys: pytest.CaptureFixture[str]) -> None:
    """Acceptance criterion 1 says *via a CLI*, so the CLI is what is tested."""
    from services.api.orchestration.__main__ import main

    register_ok("alpha_agent", Stage.EXTRACT)

    assert main([]) == 0
    assert "graph TD" in capsys.readouterr().out

    assert main(["--summary"]) == 0
    summary = capsys.readouterr().out
    assert "alpha_agent" in summary and "extract" in summary


def test_the_summary_groups_agents_by_tier() -> None:
    register_ok("extractor_one", Stage.EXTRACT)
    register_ok("investigator_one", Stage.INVESTIGATE)
    register_ok("judge_one", Stage.JUDGE)

    summary = orch.graph_summary()
    assert summary["agents"]["extract"] == ["extractor_one"]
    assert summary["agents"]["investigate"] == ["investigator_one"]
    assert summary["agents"]["judge"] == ["judge_one"]
    assert summary["agents"]["reason"] == []


# --------------------------------------------------------------------------
# 2 — a node times out and the investigation still completes
# --------------------------------------------------------------------------


def test_an_investigation_completes_with_a_node_timing_out() -> None:
    """Acceptance criterion 2, in the shape the task specifies: three nodes,
    one of them deliberately never returning."""

    @registry.register
    class Hangs(_Ok):
        name = "hangs_forever"
        version = "1.0.0"

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            await asyncio.sleep(30)
            raise AssertionError("unreachable")

    register_ok("works_fine")
    register_ok("also_works", Stage.EXTRACT)

    from services.api.orchestration.policy import POLICIES, NodePolicy

    POLICIES["hangs_forever"] = NodePolicy(timeout_s=0.1, attempts=1)
    try:
        out = run(make_state())
    finally:
        POLICIES.pop("hangs_forever", None)

    assert out.status is InvestigationStatus.COMPLETE
    assert out.completed_at is not None
    assert "agent:hangs_forever:timeout" in out.degraded

    by_agent = {r.agent: r.status for r in out.agent_results}
    assert by_agent == {
        "also_works": AgentStatus.OK,
        "hangs_forever": AgentStatus.ERROR,
        "works_fine": AgentStatus.OK,
    }
    # The agents that worked still contributed their evidence.
    assert any(r.findings for r in out.agent_results if r.agent == "works_fine")


def test_the_per_agent_policy_timeout_is_actually_applied() -> None:
    """The test that was missing, and the bug it would have caught.

    The first version of this file asserted only that a hanging agent produced
    an `agent:x:timeout` tag. It did — but at the *default* 8 s, because
    `graph.py` computed the policy and never put its timeout on the context.
    Every per-agent budget in `policy.py` was a silent no-op: threat intel's 3 s
    and the APK agent's 120 s both quietly became 8. Nothing failed; the
    investigation completed on the wrong clock, and only an end-to-end run
    noticed a feed with a 2 s policy timing out at 8002 ms.

    So this asserts the *duration*, which is the only thing that could have
    distinguished the two.
    """

    @registry.register
    class Hangs(_Ok):
        name = "policy_timeout_toy"
        version = "1.0.0"

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            await asyncio.sleep(30)
            raise AssertionError("unreachable")

    from services.api.orchestration.policy import POLICIES, NodePolicy

    POLICIES["policy_timeout_toy"] = NodePolicy(timeout_s=0.2, attempts=1)
    try:
        started = time.monotonic()
        out = run(make_state())
        elapsed = time.monotonic() - started
    finally:
        POLICIES.pop("policy_timeout_toy", None)

    assert "agent:policy_timeout_toy:timeout" in out.degraded
    assert elapsed < 2.0, (
        f"took {elapsed:.1f}s — the 0.2s policy timeout was ignored and the "
        "default was used instead"
    )
    span = next(s for s in out.trace if s.node == "investigate/policy_timeout_toy")
    assert span.latency_ms < 1500, f"span says {span.latency_ms} ms, policy said 200 ms"


def test_the_context_a_node_receives_carries_its_own_policy_budget() -> None:
    """Same defect, checked from the agent's side rather than the clock's."""
    seen: Dict[str, float] = {}

    @registry.register
    class Introspector(_Ok):
        name = "introspector_toy"
        version = "1.0.0"

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            seen["timeout_s"] = ctx.timeout_s
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    from services.api.orchestration.policy import POLICIES, NodePolicy

    POLICIES["introspector_toy"] = NodePolicy(timeout_s=3.5, attempts=1)
    try:
        run(make_state())
    finally:
        POLICIES.pop("introspector_toy", None)

    assert seen["timeout_s"] == 3.5


def test_a_cancel_signal_still_reaches_an_agent_after_the_policy_is_applied() -> None:
    """The policy is applied with `dataclasses.replace`, which copies the
    context. If it copied the cancel event too, cancelling an investigation
    would stop signalling the agents actually running."""
    captured: Dict[str, Any] = {}

    @registry.register
    class Grabber(_Ok):
        name = "grabber_toy"
        version = "1.0.0"

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            captured["cancel"] = ctx.cancel
            captured["depth"] = ctx.depth
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    run(make_state())
    assert captured["depth"] == 0, "applying a policy must not deepen the recursion"
    assert isinstance(captured["cancel"], asyncio.Event)


def test_every_agent_erroring_still_completes_rather_than_failing() -> None:
    """COMPLETE, not FAILED.

    An investigation that ran and found nothing usable is a completed
    investigation with an honest `degraded` list. FAILED is reserved for the
    orchestrator being unable to run at all, which is a different and much rarer
    thing — and reporting it here would tell a citizen the system broke when in
    fact the system worked and the evidence did not.
    """

    @registry.register
    class Boom(_Ok):
        name = "always_raises"
        version = "1.0.0"

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            raise ValueError("nope")

    out = run(make_state())
    assert out.status is InvestigationStatus.COMPLETE
    assert out.degraded == ["agent:always_raises:error"]
    assert out.agent_results[0].status is AgentStatus.ERROR


def test_an_inapplicable_agent_is_skipped_and_not_tagged() -> None:
    @registry.register
    class ApkOnly(_Ok):
        name = "apk_only_toy"
        version = "1.0.0"
        can_handle = registry.handles_input(InputType.APK)

    register_ok("text_toy")
    out = run(make_state())

    assert [r.agent for r in out.agent_results] == ["text_toy"]
    assert out.degraded == []


# --------------------------------------------------------------------------
# 3 — the trace
# --------------------------------------------------------------------------


def test_the_trace_records_a_span_per_node_with_real_latency() -> None:
    @registry.register
    class Slow(_Ok):
        name = "slow_toy"
        version = "2.1.0"

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            await asyncio.sleep(0.05)
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    register_ok("fast_toy")
    out = run(make_state())

    spans = {s.node: s for s in out.trace}
    assert "investigate/slow_toy" in spans and "investigate/fast_toy" in spans

    slow = spans["investigate/slow_toy"]
    assert slow.agent == "slow_toy" and slow.version == "2.1.0"
    assert slow.status is AgentStatus.OK
    assert slow.latency_ms >= 40, "latency is measured, not asserted"
    assert slow.t_end >= slow.t_start
    assert slow.attempt == 1 and slow.depth == 0


def test_a_retry_appears_as_two_spans_not_one() -> None:
    """A node that succeeded on its second try is not the same as one that
    succeeded first time. Overwriting the first attempt would make the latency
    percentile in 9.4 a selective average."""
    calls: List[int] = []

    @registry.register
    class Flaky(_Ok):
        name = "flaky_toy"
        version = "1.0.0"

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            calls.append(1)
            if len(calls) == 1:
                raise ConnectionError("first attempt fails transiently")
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    from services.api.orchestration.policy import POLICIES, NodePolicy

    POLICIES["flaky_toy"] = NodePolicy(timeout_s=2.0, attempts=2, backoff_s=0.01)
    try:
        out = run(make_state())
    finally:
        POLICIES.pop("flaky_toy", None)

    attempts = sorted(s.attempt for s in out.trace if s.node == "investigate/flaky_toy")
    assert attempts == [1, 2]
    assert len(calls) == 2

    first, second = (s for s in sorted(out.trace, key=lambda s: s.attempt) if s.node == "investigate/flaky_toy")
    assert first.status is AgentStatus.ERROR and "ConnectionError" in (first.error or "")
    assert second.status is AgentStatus.OK
    # The final result is the successful one, but the failure is still recorded.
    assert out.agent_results[0].status is AgentStatus.OK
    assert "agent:flaky_toy:error" in out.degraded


def test_span_ids_are_stable_and_readable() -> None:
    register_ok("stable_toy")
    a = run(make_state())
    b = run(make_state())
    assert [s.span_id for s in a.trace] == [s.span_id for s in b.trace]
    assert "investigate/stable_toy#1@0" in [s.span_id for s in a.trace]


# --------------------------------------------------------------------------
# 4 — determinism
# --------------------------------------------------------------------------


def test_two_runs_of_the_same_input_produce_one_fingerprint() -> None:
    """Acceptance criterion 4, against agents that finish in a different order
    every time.

    The randomised sleeps are the test. Without the sort in `_run_stage`,
    `agent_results` comes back in completion order — which is latency order,
    which is machine load — and this fails intermittently, which is the worst
    way for a determinism bug to be discovered.
    """

    class Jittery(_Ok):
        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            await asyncio.sleep(random.uniform(0.001, 0.05))
            return AgentResult(
                agent=self.name,
                version=self.version,
                status=AgentStatus.OK,
                features={f"{self.name}_ran": 1.0},
            )

    for n in ("zulu_toy", "alpha_toy", "mike_toy", "bravo_toy"):
        registry.register(type("J", (Jittery,), {"name": n}))

    first = run(make_state())
    second = run(make_state())

    assert fingerprint(first) == fingerprint(second), diff_summary(first, second)
    assert [r.agent for r in first.agent_results] == ["alpha_toy", "bravo_toy", "mike_toy", "zulu_toy"]


def test_the_fingerprint_notices_a_real_change() -> None:
    """A hash that never moves is not evidence of determinism, it is a bug."""
    register_ok("only_toy")
    baseline = run(make_state())

    changed = baseline.model_copy(deep=True)
    changed.agent_results[0].features["injected"] = 1.0
    assert fingerprint(changed) != fingerprint(baseline)
    assert "agent_results" in diff_summary(baseline, changed)


def test_the_fingerprint_ignores_only_the_timings() -> None:
    register_ok("timing_toy")
    baseline = run(make_state())

    retimed = baseline.model_copy(deep=True)
    for span in retimed.trace:
        span.latency_ms += 999
        span.t_start += 1.0
        span.t_end += 1.0
    for result in retimed.agent_results:
        result.latency_ms += 999
    retimed.completed_at = "2099-01-01T00:00:00Z"

    assert fingerprint(retimed) == fingerprint(baseline)


def test_excluding_an_agent_changes_the_result_and_nothing_else_does() -> None:
    """What makes an ablation valid: the only thing that differs is the thing
    that was removed."""
    register_ok("kept_toy")
    register_ok("ablated_toy")

    full_a, full_b = run(make_state()), run(make_state())
    ablated = run(make_state(), exclude=["ablated_toy"])

    assert fingerprint(full_a) == fingerprint(full_b)
    assert fingerprint(ablated) != fingerprint(full_a)
    assert [r.agent for r in ablated.agent_results] == ["kept_toy"]


# --------------------------------------------------------------------------
# Tier ordering and concurrency
# --------------------------------------------------------------------------


def test_tiers_run_in_order_and_agents_within_a_tier_run_concurrently() -> None:
    """Extraction must finish before investigation starts — investigation works
    on what extraction produced. Within a tier, concurrency is the difference
    between a 4-second and a 25-second investigation (ARCHITECTURE.md §2)."""
    order: List[str] = []

    class Recorder(_Ok):
        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            order.append(f"{self.stage.value}:{self.name}:start")
            await asyncio.sleep(0.05)
            order.append(f"{self.stage.value}:{self.name}:end")
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    registry.register(type("E", (Recorder,), {"name": "ex_one", "stage": Stage.EXTRACT}))
    registry.register(type("I1", (Recorder,), {"name": "inv_one", "stage": Stage.INVESTIGATE}))
    registry.register(type("I2", (Recorder,), {"name": "inv_two", "stage": Stage.INVESTIGATE}))

    run(make_state())

    assert order[0] == "extract:ex_one:start"
    assert order[1] == "extract:ex_one:end"
    # Both investigate agents start before either finishes — that is concurrency.
    assert set(order[2:4]) == {"investigate:inv_one:start", "investigate:inv_two:start"}


def test_an_agent_sees_what_an_earlier_tier_wrote() -> None:
    """The tiers exist so later agents can read earlier results."""
    seen: Dict[str, int] = {}

    @registry.register
    class Extractor(_Ok):
        name = "the_extractor"
        version = "1.0.0"
        stage = Stage.EXTRACT

    @registry.register
    class Reader(_Ok):
        name = "the_reader"
        version = "1.0.0"
        stage = Stage.JUDGE

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            seen["count"] = len(state.agent_results)
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    run(make_state())
    assert seen["count"] == 1, "the judge tier could not see the extract tier's result"


# --------------------------------------------------------------------------
# Checkpointing
# --------------------------------------------------------------------------


def test_a_crashed_investigation_resumes_without_re_running_finished_nodes() -> None:
    """ADR-0004's fourth rationale, made real.

    The agent is asked to explode once. After the crash the checkpoint holds the
    completed tier; resuming continues from there, and the extract agent is not
    called a second time — which is what makes a 120-second APK scan survivable.
    """
    calls: List[str] = []
    explode = {"now": True}

    @registry.register
    class Extractor(_Ok):
        name = "resume_extract"
        version = "1.0.0"
        stage = Stage.EXTRACT

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            calls.append("extract")
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    @registry.register
    class Investigator(_Ok):
        name = "resume_investigate"
        version = "1.0.0"

        async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
            calls.append("investigate")
            if explode["now"]:
                raise SystemExit("process died mid-investigation")
            return AgentResult(agent=self.name, version=self.version, status=AgentStatus.OK)

    saver = orch.new_checkpointer()
    state = make_state()

    with pytest.raises(SystemExit):
        asyncio.run(orch.investigate(state, checkpointer=saver, thread_id="case-resume"))

    assert calls == ["extract", "investigate"]

    explode["now"] = False
    out = asyncio.run(orch.resume(saver, "case-resume"))

    assert out.status is InvestigationStatus.COMPLETE
    assert calls == ["extract", "investigate", "investigate"], (
        "the extract tier was re-run; the checkpoint did not hold"
    )
    assert {r.agent for r in out.agent_results} == {"resume_extract", "resume_investigate"}


def test_running_without_a_checkpointer_needs_no_thread_id() -> None:
    """The common path stays simple — durability is opt-in, not mandatory."""
    register_ok("plain_toy")
    out = run(make_state())
    assert out.status is InvestigationStatus.COMPLETE
