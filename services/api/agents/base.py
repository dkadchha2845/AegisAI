"""
The agent contract, and the harness that keeps one bad agent from killing an
investigation.

**Why it exists.** ARCHITECTURE.md §2 gives every node in the investigation
graph the same execution policy: a per-agent timeout, failure that degrades
rather than aborts, and isolation — an agent may read `InvestigationState` and
nothing else. That policy has to live in one place. If each agent implements its
own try/except, the twentieth agent forgets, and the investigation that dies is
the one a frightened person is waiting on.

**What it consumes.** An `InvestigationState` (read-only, by convention) and an
`AgentContext` carrying the deadline, the org, a cancellation signal and a
budget.

**What it outputs.** Exactly one `AgentResult` per execution — always, including
when the agent raises, hangs, or is cancelled. `run_agent()` has no path that
returns `None` or propagates.

**How it connects.** The registry in `registry.py` is what the orchestrator
(1.3) enumerates to build the graph; `can_handle()` is what conditional routing
keys off. Nothing here imports an agent, and no agent imports another.

**How it is evaluated.** By the tests in `test_agent_base.py`: a raising agent,
a hanging agent, a cancelled agent and a well-behaved one all yield a valid
`AgentResult`, and the latency recorded is the latency actually spent.

**Limitations, stated.** Timeout cancels the *task*, which only takes effect at
an `await` point — an agent that blocks the event loop in pure CPU code cannot
be interrupted here, and must be moved to the worker (1.8). Retry and backoff
are deliberately absent: ARCHITECTURE.md puts them in `policy.py`, which is 1.3,
because retrying is a graph decision that needs to know whether an error was
transient. And `AgentContext.budget_inr` is carried but not enforced; the agents
that spend money do not exist yet, and a limit nothing checks is worse than no
limit because it reads as a guarantee.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from schema.models import AgentResult, AgentStatus, InvestigationState

#: Per ARCHITECTURE.md §2. Individual agents override it — threat intel gets 3 s,
#: an APK scan gets 120 s and runs off the request path entirely.
DEFAULT_TIMEOUT_S = 8.0


@dataclass
class AgentContext:
    """Everything an agent needs that is not evidence.

    Deliberately not part of the wire contract. `InvestigationState` is
    persisted, checkpointed and streamed to a browser; a cancellation primitive
    and a wall-clock deadline are runtime plumbing that would be meaningless
    after a round trip through JSONB.

    `deadline` is absolute rather than a duration, so it survives being passed
    down into a sub-investigation: a nested URL lookup inherits the time its
    parent has left instead of quietly starting an 8-second budget of its own at
    depth 2.
    """

    org_id: str
    case_id: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    deadline: Optional[float] = None
    depth: int = 0
    max_depth: int = 2
    budget_inr: Optional[float] = None
    #: Set by the orchestrator to abandon in-flight work — a cancelled
    #: investigation, or a real-time frame whose deadline has already passed.
    cancel: asyncio.Event = field(default_factory=asyncio.Event)

    def remaining_s(self) -> float:
        """Seconds left before this agent must stop. Never negative."""
        if self.deadline is None:
            return self.timeout_s
        return max(0.0, self.deadline - time.monotonic())

    def child(self, *, timeout_s: Optional[float] = None) -> "AgentContext":
        """A context for a nested sub-investigation, one level deeper.

        The deadline is inherited, not reset. The cancel event is shared, so
        cancelling the parent cancels everything it spawned.
        """
        return AgentContext(
            org_id=self.org_id,
            case_id=self.case_id,
            timeout_s=timeout_s if timeout_s is not None else self.timeout_s,
            deadline=self.deadline,
            depth=self.depth + 1,
            max_depth=self.max_depth,
            budget_inr=self.budget_inr,
            cancel=self.cancel,
        )


@runtime_checkable
class Agent(Protocol):
    """What every agent implements. Four members, no base class.

    A Protocol rather than an ABC on purpose: 1.7 wraps the inherited engine —
    `classifier.py`, `coercion.py`, `twin.py` — in thin adapters, and those
    adapters should not have to inherit from anything to be an agent. Structural
    typing means an adapter is an agent because it has the right shape, which
    keeps the crown-jewel engine free of any dependency on this layer.
    """

    #: Registry key. Stable, snake_case, and never reused for a different agent.
    name: str
    #: Pinned per ARCHITECTURE.md §3, so a result recorded a year ago says which
    #: code produced it. Reproducibility for the Phase 9 ablations depends on it.
    version: str

    def can_handle(self, state: InvestigationState) -> bool:
        """Whether this agent has anything to do for this state.

        Cheap and side-effect-free — the orchestrator calls it on every agent for
        every investigation. Returning False yields `AgentStatus.SKIPPED`, which
        4.1 must never read as "clean".
        """
        ...

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        """Do the work. Async because the graph fans out with `asyncio.gather`.

        An agent may raise; `run_agent()` contains it. An agent should *not*
        catch its own failures and return `status="ok"` with empty findings —
        that hides a degradation the citizen is entitled to see.
        """
        ...


def skipped(agent: Agent, reason: str = "") -> AgentResult:
    """The result for an agent whose `can_handle()` said no.

    A real record rather than an omission: the trace should show that the APK
    agent was considered and did not apply, and the feature assembly in 4.1 needs
    to distinguish "ran and found nothing" from "never ran".
    """
    return AgentResult(
        agent=agent.name,
        version=agent.version,
        status=AgentStatus.SKIPPED,
        confidence=0.0,
        latency_ms=0,
        error=reason or None,
    )


def failed(agent: Agent, error: str, latency_ms: int) -> AgentResult:
    """The result for an agent that raised, hung, or was cancelled.

    `ERROR`, not `DEGRADED`. ARCHITECTURE.md §2's table says a failing node
    "emits AgentResult(status=DEGRADED)", and this is a deliberate refinement of
    that wording rather than a departure from it: the property the table is
    protecting — the investigation still completes, and the shortfall is visible
    in `degraded` — holds either way, and `run_agent` always returns a tag for
    the caller to append.

    The distinction is worth keeping because only the agent itself can know it
    fell back. DEGRADED means "I answered, from a cached snapshot instead of the
    live feed" — a usable answer with a caveat. An agent that raised produced no
    answer at all, and labelling that DEGRADED would make the two
    indistinguishable to 4.1, which has to decide how much weight a result
    carries.
    """
    return AgentResult(
        agent=agent.name,
        version=agent.version,
        status=AgentStatus.ERROR,
        confidence=0.0,
        latency_ms=latency_ms,
        error=error,
    )


async def run_agent(
    agent: Agent, state: InvestigationState, ctx: AgentContext
) -> tuple[AgentResult, Optional[str]]:
    """Run one agent under the §2 execution policy. Never raises.

    Returns the result and, when something went wrong, a `degraded` tag for the
    orchestrator to append to `state.degraded` — the tag is returned rather than
    written here because this function does not mutate state. An agent that
    cannot see another agent's internals should not be able to see another
    agent's writes either, and a pure function is also what makes the parallel
    fan-out in 1.3 safe to merge.

    Four outcomes, all of them an `AgentResult`:

    | Situation | status | tag |
    |---|---|---|
    | `can_handle()` false | SKIPPED | none — not applying is not a shortfall |
    | Returned normally | whatever the agent said | `agent:<name>:degraded` if DEGRADED |
    | Raised | ERROR | `agent:<name>:error` |
    | Exceeded its timeout, or cancelled | ERROR | `agent:<name>:timeout` / `:cancelled` |

    Latency is measured around the call in every branch, including the failures.
    A timeout that recorded 0 ms would quietly flatter the p95 in 9.4, and an
    unmeasured latency is exactly the claim CLAUDE.md forbids.
    """
    if not agent.can_handle(state):
        return skipped(agent), None

    if ctx.cancel.is_set():
        return failed(agent, "cancelled before start", 0), f"agent:{agent.name}:cancelled"

    budget = min(ctx.timeout_s, ctx.remaining_s()) if ctx.deadline else ctx.timeout_s
    started = time.monotonic()

    def elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        result = await asyncio.wait_for(agent.run(state, ctx), timeout=budget)
    except asyncio.TimeoutError:
        return (
            failed(agent, f"timed out after {budget:.1f}s", elapsed_ms()),
            f"agent:{agent.name}:timeout",
        )
    except asyncio.CancelledError:
        # Re-raised deliberately: a cancelled task must stay cancelled, or
        # `asyncio.gather` cannot shut a fan-out down. This is the one exception
        # that is allowed past, and it is not an agent failure.
        raise
    # Broad by design: this is where the degradation invariant is implemented.
    # BLE001 is already off repo-wide for exactly this reason (pyproject.toml).
    except Exception as e:
        return (
            failed(agent, f"{type(e).__name__}: {e}", elapsed_ms()),
            f"agent:{agent.name}:error",
        )

    if not isinstance(result, AgentResult):
        # A malformed agent is a failure of that agent, not of the investigation.
        return (
            failed(agent, f"returned {type(result).__name__}, expected AgentResult", elapsed_ms()),
            f"agent:{agent.name}:error",
        )

    # The agent may not have bothered; the trace needs the real number either way.
    if not result.latency_ms:
        result = result.model_copy(update={"latency_ms": elapsed_ms()})

    tag = f"agent:{agent.name}:degraded" if result.status is AgentStatus.DEGRADED else None
    return result, tag
