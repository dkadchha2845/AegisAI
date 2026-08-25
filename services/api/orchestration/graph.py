"""
The investigation graph — ARCHITECTURE.md §2, built from the registry.

**Why it exists.** An investigation branches. An APK agent must not run on an
audio file; URL, financial and threat-intel lookups are independent and should
run at the same time; a node that dies must not take the investigation with it.
A pipeline cannot express any of that. This is the skeleton every later phase
plugs into: Phase 2 adds agents and the graph gains nodes without being edited.

**What it consumes.** An `InvestigationState` and the agent registry.

**What it outputs.** The same state, advanced — `agent_results`, `trace` and
`degraded` populated, `status` moved to COMPLETE.

**How it connects.** Nodes are tiers from `agents/base.Stage`; membership comes
from `registry.eligible()`, which is `can_handle()`, which keys off
`input_types`. The lifecycle API (task 1.6) drives this through
`investigate_stream()` and persists what it produces through 1.5's
`stores/evidence.py`; the graph itself still writes nothing down, which is why
`investigations/runner.py` exists rather than a `save()` call in `finish`.

**How it is evaluated.** `test_orchestration_graph.py` — compiles, renders to
Mermaid, completes with a node deliberately timing out, records a span per
attempt, resumes from a checkpoint after a crash, and produces an identical
fingerprint across runs. `test_investigations_api.py` covers the streaming
entry point end to end.

**Limitations, stated.** The `FAN -.new entity discovered.-> FAN` loop in §2 is
*not* implemented. `AgentContext.max_depth` is carried and enforced, so the
bound exists, but nothing yet discovers an entity worth recursing on — that
needs the Phase 2 agents, and building the loop now would mean testing it
against a toy that pretends. The judgement tier is a real node with no agents
in it yet; 4.6 and 4.7 fill it, so an investigation completes today with
`risk_score` still None — unscored, which the report says rather than rendering
as zero. Nothing here persists: the state comes back to the caller, and 1.5's
`EvidenceStore` is what writes it down.

Why LangGraph owns the graph but not the fan-out
------------------------------------------------
LangGraph provides the state machine, the conditional edges, the checkpointer
and the Mermaid rendering — the things ADR-0004 chose it for. The concurrency
inside a tier is `asyncio.gather` here rather than parallel LangGraph nodes, for
two reasons that both matter more than the symmetry.

First, parallel LangGraph branches writing the same state key need a reducer
declared on the state schema, as `Annotated[list, add]`. That schema is
`InvestigationState`, which lives in `schema/` and is mirrored into TypeScript.
Putting orchestration metadata into the shared contract to satisfy one library
is exactly the leak the contract exists to prevent.

Second, the merge order would then be the library's business, and determinism is
ours: the results here are sorted by agent name before they are appended, so two
runs of the same input produce the same list in the same order.
"""

from __future__ import annotations

import asyncio
import warnings
from dataclasses import dataclass, replace
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

# langgraph's import trips a LangChainPendingDeprecationWarning about an
# `allowed_objects` argument on a deserializer we never call.
#
# It cannot be filtered from pyproject.toml, and the order is the reason:
# `langchain_core/__init__.py` calls surface_langchain_deprecation_warnings(),
# which *prepends* a "default" filter for its own categories. Filters are
# matched front-first, so anything configured earlier loses — `-W ignore:...`
# on the command line does not suppress it either. The only thing that works is
# to import langchain_core first, let it arm its filter, install ours in front
# of it, and only then import langgraph.
#
# `catch_warnings` restoring the filter list afterwards is a second, deliberate
# benefit: it undoes langchain's mutation of this process's global warning
# state, which an application has every right to want back.
with warnings.catch_warnings():
    try:
        import langchain_core  # noqa: F401  (arms its own filter on import)
    except ImportError:  # pragma: no cover - langgraph always brings it
        pass
    warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph

from schema.models import (
    AgentResult,
    AgentStatus,
    InputType,
    InvestigationState,
    InvestigationStatus,
    utc_now_iso,
)
from services.api.agents import registry
from services.api.agents.base import STAGE_ORDER, Agent, AgentContext, run_agent, stage_of
from services.api.agents.base import Stage as AgentStage
from services.api.agents.classify.agent import apply_to_state
from services.api.orchestration.determinism import fingerprint
from services.api.orchestration.policy import NodePolicy, policy_for, should_retry
from services.api.orchestration.trace import TraceRecorder

#: The whole investigation's budget. An individual agent's timeout bounds one
#: node; this bounds the sum, so a graph of twelve well-behaved-but-slow agents
#: cannot add up to a wait nobody would tolerate.
DEFAULT_BUDGET_S = 45.0

# This agent is special only in graph position, not in the execution contract:
# it still runs through `_run_with_retry`, produces an AgentResult, gets a
# trace span and has a pinned version.  It must precede EXTRACT, though, because
# every other agent's `can_handle()` reads the types it writes.
INPUT_CLASSIFIER = "input_classifier"


async def _run_with_retry(
    agent: Agent,
    state: InvestigationState,
    ctx: AgentContext,
    policy: NodePolicy,
    recorder: TraceRecorder,
    node: str,
) -> Tuple[AgentResult, List[str]]:
    """One node: up to `policy.attempts` tries, a span recorded for each.

    Returns the last result and every degraded tag collected along the way —
    including the tags from attempts that were later superseded by a success.
    That is deliberate: an agent that only worked on the second try did degrade,
    the citizen's answer was slower for it, and hiding the first failure would
    make the trace disagree with the latency.
    """
    tags: List[str] = []
    result: AgentResult
    tag: Optional[str]

    # The policy's timeout has to be put *on the context*, because that is what
    # `run_agent` reads. Computing `policy_for(agent)` and then not applying it
    # here is a silent no-op: every agent gets DEFAULT_TIMEOUT_S, the 3-second
    # threat-intel budget and the 120-second APK budget both quietly become 8,
    # and nothing fails — the investigation still completes, just on the wrong
    # clock. That is exactly what happened until an end-to-end run showed a feed
    # with a 2 s policy timing out at 8002 ms.
    #
    # `replace` rather than a new AgentContext so the cancel event stays the
    # same object: cancelling the investigation must still cancel this agent.
    ctx = replace(ctx, timeout_s=policy.timeout_s)

    for attempt in range(1, policy.attempts + 1):
        wait = policy.backoff_before(attempt)
        if wait:
            await asyncio.sleep(wait)

        t_start = recorder.now()
        result, tag = await run_agent(agent, state, ctx)
        t_end = recorder.now()

        recorder.append(
            node=node,
            agent=agent.name,
            version=agent.version,
            status=result.status,
            t_start=t_start,
            t_end=t_end,
            latency_ms=result.latency_ms,
            attempt=attempt,
            depth=ctx.depth,
            error=result.error,
        )
        if tag:
            tags.append(tag)

        if not should_retry(result, tag, attempt, policy):
            return result, tags

    return result, tags


async def _run_stage(
    stage: AgentStage,
    state: InvestigationState,
    ctx: AgentContext,
    recorder: TraceRecorder,
    exclude: Sequence[str] = (),
) -> Dict[str, Any]:
    """Fan out over every eligible agent in one tier, concurrently.

    The two orderings that matter:

    * agents are planned in registry order, which is sorted by name, so the
      span ids are assigned before anything runs;
    * results are re-sorted by agent name before they are appended, so the
      merged list does not depend on which agent finished first.

    Without the second, `agent_results` comes back in completion order — which
    is latency order, which is machine load — and two runs of the same input
    disagree.
    """
    agents = [a for a in registry.eligible(state, exclude=exclude) if stage_of(a) is stage]
    if not agents:
        return {}

    node_names = {a.name: f"{stage.value}/{a.name}" for a in agents}

    outcomes = await asyncio.gather(
        *(
            _run_with_retry(a, state, ctx, policy_for(a), recorder, node_names[a.name])
            for a in agents
        )
    )

    paired = sorted(zip([a.name for a in agents], outcomes), key=lambda p: p[0])
    results = [outcome[0] for _, outcome in paired]
    tags = [t for _, outcome in paired for t in outcome[1]]

    return {
        "agent_results": [*state.agent_results, *results],
        "degraded": [*state.degraded, *tags],
        "trace": recorder.ordered(),
    }


def _unknown_input_fallback(state: InvestigationState) -> Dict[str, Any]:
    """Route a classifier failure safely, without trusting caller-supplied type.

    `UNKNOWN` has a deliberate routing meaning in the investigation contract:
    the text agent is the only safe, generic handler.  Leaving the initial
    `input_types` in place after the classifier timed out would instead treat
    an unverified caller claim as a fact, which defeats magic-byte validation.
    """
    if not state.inputs:
        return {"input_types": []}
    return {
        "inputs": [
            item.model_copy(update={"kind": InputType.UNKNOWN})
            for item in state.inputs
        ],
        "input_types": [InputType.TEXT, InputType.UNKNOWN],
    }


def build_graph(
    *,
    checkpointer: Optional[Any] = None,
    exclude: Sequence[str] = (),
    budget_s: float = DEFAULT_BUDGET_S,
    recorder: Optional[TraceRecorder] = None,
) -> Any:
    """Compile the investigation graph.

    One node per tier rather than one per agent. The §2 diagram draws agents as
    nodes, and this draws the tiers they sit in, because tier membership is what
    the registry actually knows — an agent declares its tier, and the graph
    discovers the rest. Drawing one LangGraph node per agent would mean
    rebuilding the graph object whenever the registry changes, and the fan-out
    inside a tier is concurrent anyway, so the picture would suggest a structure
    the execution does not have.

    `exclude` is threaded through for the Phase 9 ablations: "the same graph
    without the knowledge-graph agent" is a parameter, not a branch.
    """
    rec = recorder if recorder is not None else TraceRecorder()

    async def classify(state: InvestigationState) -> Dict[str, Any]:
        """Run the one agent whose output changes subsequent routing.

        Tests deliberately clear the registry to exercise an empty graph.  In
        that narrow setup there is no built-in classifier to execute, so leave
        the state alone.  In the live process `services.api.agents` imports and
        registers it at startup; a runtime execution error then takes the
        explicit UNKNOWN-to-text fallback below.
        """
        if INPUT_CLASSIFIER in exclude or INPUT_CLASSIFIER not in registry.names():
            return {}

        agent = registry.get(INPUT_CLASSIFIER)
        ctx = AgentContext(
            org_id=state.org_id,
            case_id=state.case_id,
            deadline=rec.origin + budget_s,
        )
        result, tags = await _run_with_retry(
            agent,
            state,
            ctx,
            policy_for(agent),
            rec,
            INPUT_CLASSIFIER,
        )
        update: Dict[str, Any] = {
            "agent_results": [*state.agent_results, result],
            "degraded": [*state.degraded, *tags],
            "trace": rec.ordered(),
        }
        if result.status is AgentStatus.OK:
            update.update(apply_to_state(state, result))
        elif result.status is not AgentStatus.SKIPPED:
            update.update(_unknown_input_fallback(state))
        return update

    def make_stage_node(stage: AgentStage) -> Callable[[InvestigationState], Awaitable[Dict[str, Any]]]:
        async def node(state: InvestigationState) -> Dict[str, Any]:
            ctx = AgentContext(
                org_id=state.org_id,
                case_id=state.case_id,
                deadline=rec.origin + budget_s,
            )
            # The classifier has already run in its dedicated node.  Leaving it
            # eligible here would produce duplicate findings and trace spans,
            # then make its own updated input types look like a second input.
            return await _run_stage(
                stage,
                state,
                ctx,
                rec,
                exclude=(*exclude, INPUT_CLASSIFIER),
            )

        node.__name__ = f"{stage.value}_stage"
        return node

    async def begin(state: InvestigationState) -> Dict[str, Any]:
        return {"status": InvestigationStatus.RUNNING}

    async def finish(state: InvestigationState) -> Dict[str, Any]:
        # COMPLETE, not FAILED, even when every agent errored. An investigation
        # that ran and found nothing usable is a completed investigation with an
        # honest `degraded` list — the degradation invariant, at the top level.
        # FAILED is reserved for the orchestrator itself being unable to run,
        # which is a different and much rarer thing.
        return {
            "status": InvestigationStatus.COMPLETE,
            "completed_at": utc_now_iso(),
            "trace": rec.ordered(),
        }

    g: Any = StateGraph(InvestigationState)
    g.add_node("begin", begin)
    g.add_node("classify", classify)
    for stage in STAGE_ORDER:
        g.add_node(f"{stage.value}_stage", make_stage_node(stage))
    g.add_node("finish", finish)

    g.add_edge(START, "begin")
    g.add_edge("begin", "classify")
    previous = "classify"
    for stage in STAGE_ORDER:
        g.add_edge(previous, f"{stage.value}_stage")
        previous = f"{stage.value}_stage"
    g.add_edge(previous, "finish")
    g.add_edge("finish", END)

    return g.compile(checkpointer=checkpointer)


def node_plan() -> List[str]:
    """Every node a run executes, in order.

    Knowable before anything runs because the graph is built from tiers rather
    than from agents, and that is the whole point: the lifecycle API sends this
    list to the client on `accepted`, so a progress bar has a real denominator.
    Without it the UI would have to guess how many steps are left, which is the
    fake timer task 1.9 forbids.
    """
    return ["begin", "classify", *(f"{s.value}_stage" for s in STAGE_ORDER), "finish"]


@dataclass(frozen=True)
class NodeUpdate:
    """One graph node, finished.

    `update` is exactly what the node returned — the keys it wrote and nothing
    else — so a consumer can tell "this tier produced two agent results" from
    "this tier was empty" without diffing whole states.

    `state` is the whole investigation as it stands after this node — attached
    rather than yielded as a separate sentinel, so the stream is one event per
    node with no phantom extra step. It is None for a node that wrote nothing
    (an empty tier, where no agent was eligible), because the graph emits no
    new snapshot for one and inventing a duplicate would suggest something
    happened. It is always set on the last update, which is the finished
    investigation.
    """

    node: str
    update: Mapping[str, Any]
    state: Optional[InvestigationState] = None


async def investigate_stream(
    state: InvestigationState,
    *,
    exclude: Sequence[str] = (),
    budget_s: float = DEFAULT_BUDGET_S,
    checkpointer: Optional[Any] = None,
    thread_id: Optional[str] = None,
) -> AsyncIterator[NodeUpdate]:
    """Run one investigation, yielding a `NodeUpdate` as each node completes.

    This is what `GET /api/investigations/{id}/stream` is built on, and the
    reason progress is observed rather than estimated: LangGraph reports a node
    when the node is actually done, so a tier that took nine seconds shows as
    nine seconds of nothing followed by a real completion — which is the truth,
    and is more useful than a bar that moves smoothly and means nothing.

    Two stream modes are requested together. `updates` names the node and gives
    what it wrote; `values` gives the full state after each superstep, and the
    last one is the finished investigation. Reconstructing the final state by
    accumulating the updates instead would work today and break silently the
    first time a channel gets a reducer, because the update would then be a
    fragment to merge rather than a value to overwrite.
    """
    recorder = TraceRecorder()
    compiled = build_graph(
        checkpointer=checkpointer, exclude=exclude, budget_s=budget_s, recorder=recorder
    )
    config = {"configurable": {"thread_id": thread_id or state.case_id}} if checkpointer else None

    seen_values = False
    pending: Optional[NodeUpdate] = None

    async for mode, payload in compiled.astream(state, config, stream_mode=["updates", "values"]):
        if mode == "values":
            # A snapshot always arrives *after* the `updates` frame of the node
            # that produced it, so it belongs to whatever is pending. Holding
            # each update back by one is what lets it be attached there instead
            # of arriving as an orphan after the last node.
            seen_values = True
            if pending is not None:
                pending = replace(pending, state=InvestigationState.model_validate(payload))
            continue
        for node, update in (payload or {}).items():
            if pending is not None:
                yield pending
            pending = NodeUpdate(node=node, update=update or {})

    if pending is None:  # pragma: no cover - `begin` and `finish` always run
        raise RuntimeError("the investigation graph executed no nodes")
    if pending.state is None or not seen_values:  # pragma: no cover - `finish` always writes
        raise RuntimeError("the investigation graph produced no final state")

    yield pending


async def investigate(
    state: InvestigationState,
    *,
    exclude: Sequence[str] = (),
    budget_s: float = DEFAULT_BUDGET_S,
    checkpointer: Optional[Any] = None,
    thread_id: Optional[str] = None,
) -> InvestigationState:
    """Run one investigation to completion. The entry point 1.6 calls.

    Returns a real `InvestigationState`, not LangGraph's dict: the library's
    output shape is an implementation detail, and every caller downstream is
    typed against the contract.

    Implemented on `investigate_stream` rather than beside it. Two entry points
    into one graph is two execution paths that have to be kept behaving
    identically by hand, and the day they diverge is the day a bug reproduces
    over SSE and not in the test that calls this.
    """
    final: Optional[InvestigationState] = None
    async for update in investigate_stream(
        state,
        exclude=exclude,
        budget_s=budget_s,
        checkpointer=checkpointer,
        thread_id=thread_id,
    ):
        if update.state is not None:
            final = update.state
    if final is None:  # pragma: no cover - investigate_stream raises first
        raise RuntimeError("the investigation graph produced no final state")
    return final


async def resume(
    checkpointer: Any, thread_id: str, *, exclude: Sequence[str] = ()
) -> InvestigationState:
    """Continue an investigation that died part-way through.

    The nodes that already completed are not re-run — LangGraph replays from the
    last checkpoint. That is what task 1.8's "worker crash loses no work" will
    stand on, and what makes a 120-second APK scan survivable.
    """
    compiled = build_graph(checkpointer=checkpointer, exclude=exclude)
    raw = await compiled.ainvoke(None, {"configurable": {"thread_id": thread_id}})
    return InvestigationState.model_validate(raw)


def new_checkpointer() -> Any:
    """In-memory. Still in-memory after 1.5, and this says so rather than
    pointing at a task that has already shipped.

    1.5 built the evidence store — the durable record of a *finished*
    investigation — not a durable checkpointer. They are different things: the
    store answers "what did this investigation conclude", a checkpointer answers
    "which node was it on when the process died". LangGraph's Postgres saver is
    its own package with its own schema and its own migrations, and the task
    that needs it is 1.8, where a 90-second APK scan runs off the request path
    and "worker crash loses no work" is an acceptance criterion rather than a
    nice property.

    So: in-process means a crash that takes the process takes the checkpoint
    too. Today this buys resume-after-agent-crash, not resume-after-restart.
    Saying which of the two you have is the difference between a durability
    claim and a durability guess.
    """
    return InMemorySaver()


def render_mermaid(*, exclude: Sequence[str] = ()) -> str:
    """The graph as Mermaid. Acceptance criterion for 1.3, and a paper figure."""
    return str(build_graph(exclude=exclude).get_graph().draw_mermaid())


def graph_summary() -> Dict[str, Any]:
    """What the graph would do right now, without running it.

    Useful in `/api/health` and when a reviewer asks which agents are live.
    """
    by_stage: Dict[str, List[str]] = {s.value: [] for s in STAGE_ORDER}
    for agent in registry.all_agents():
        by_stage[stage_of(agent).value].append(agent.name)
    return {
        "stages": [s.value for s in STAGE_ORDER],
        "agents": by_stage,
        "versions": registry.versions(),
        "budget_s": DEFAULT_BUDGET_S,
    }


__all__ = [
    "DEFAULT_BUDGET_S",
    "INPUT_CLASSIFIER",
    "NodeUpdate",
    "build_graph",
    "fingerprint",
    "graph_summary",
    "investigate",
    "investigate_stream",
    "new_checkpointer",
    "node_plan",
    "render_mermaid",
    "resume",
]
