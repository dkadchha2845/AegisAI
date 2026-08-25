"""
Driving one investigation, and saying what it is doing while it does it.

**Why it exists.** Task 1.6's first acceptance criterion is "submit → live
per-node progress → final report, end to end". Three things have to be true at
once for that sentence: the request must return before the graph finishes, the
progress must be *observed* rather than estimated, and a client that drops its
connection must be able to come back without seeing anything twice. This module
is where all three are arranged.

**What it consumes.** An `InvestigationState` that intake has already built, and
1.3's `investigate_stream()`.

**What it outputs.** A `Run`: a journal of `InvestigationEvent`s with monotonic
sequence numbers, the freshest state, and a durable save through 1.5's
`EvidenceStore` when the graph finishes.

**How it connects.** `routes/investigations.py` starts a run, follows its
journal for SSE, and reads its state for `GET /{id}`. Nothing else touches it.

**How it is evaluated.** `test_investigations_api.py`: a run emits one event per
graph node with contiguous sequence numbers, a follower that reconnects with
`Last-Event-ID` receives the remainder and no duplicate, a follower that arrives
after the run finished is replayed the whole journal, a cancelled run stops,
and a store that refuses the write degrades the investigation instead of losing
the answer.

**Limitations, stated.** Execution is **in this process**, on the event loop
that serves requests. That is what task 1.8 replaces with Redis and Celery, and
until it does, three things are true and should be said rather than discovered:
a restart loses every in-flight run (the durable record then says QUEUED
forever, because nothing is left to move it on); the journal is in memory, so a
client reconnecting after a restart gets a 404 on the stream even though
`GET /{id}` and the report still work from the database; and a genuinely slow
agent occupies a worker slot. The shape here — start, journal, follow, persist —
is deliberately the shape a queue backend would keep, so 1.8 changes where
`_drive` runs and not what a route calls.

Why the journal is a list and not a queue
-----------------------------------------
A queue per subscriber is the usual way to fan out events, and it makes the
reconnect requirement unsatisfiable: once an event has been taken off a queue it
is gone, so a client that dropped between two events has no way to ask for what
it missed, and the server has no way to know whether it should. Keeping the
whole journal and having each follower hold an *index* into it turns reconnect
into arithmetic — `Last-Event-ID: 4` means "resume from index 4" — and makes
"without duplicate events" a property of the data structure rather than a
promise about timing.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from schema.models import (
    AgentResult,
    InvestigationEvent,
    InvestigationEventKind,
    InvestigationState,
    InvestigationStatus,
    utc_now_iso,
)

from ..db import SessionLocal
from ..orchestration.graph import investigate_stream, node_plan
from ..stores.evidence import EvidenceStore

#: How long a follower waits before the stream emits a keepalive. SSE comment
#: lines carry no id, so a keepalive can never be replayed or duplicated — which
#: is why the idle path uses one instead of a synthetic heartbeat event.
KEEPALIVE_S = 15.0

#: Finished runs are kept this long so a client that reconnects late can still
#: be replayed. After that the journal is dropped; the case itself is durable in
#: the evidence store, so what is lost is the per-node timeline, not the answer.
RETAIN_S = 30 * 60.0

#: A ceiling on remembered runs, so a busy process cannot accumulate journals
#: without bound. Oldest finished run goes first; a running one is never evicted.
MAX_RUNS = 128

#: Recorded on the investigation when the final save fails. The answer still
#: reached the caller over the stream; what was lost is its durability, and the
#: distinction belongs in `degraded` rather than in a 500.
WRITE_FAILED = "store:evidence:write_failed"


class Run:
    """One investigation in flight, plus everything anyone may still ask about it."""

    def __init__(self, state: InvestigationState, org_id: str) -> None:
        self.case_id = state.case_id
        self.org_id = org_id
        self.state = state
        self.plan: List[str] = node_plan()
        self.started_monotonic = time.monotonic()
        self.finished_monotonic: Optional[float] = None
        self.task: Optional["asyncio.Task[None]"] = None

        self._events: List[InvestigationEvent] = []
        self._bell = asyncio.Event()
        self._nodes_done = 0
        self._agents_seen = 0
        self._degraded_seen = 0

    # -- journal -----------------------------------------------------------

    @property
    def events(self) -> List[InvestigationEvent]:
        return list(self._events)

    @property
    def finished(self) -> bool:
        return self.finished_monotonic is not None

    def append(
        self,
        kind: InvestigationEventKind,
        *,
        status: Optional[InvestigationStatus] = None,
        node: Optional[str] = None,
        plan: Optional[List[str]] = None,
        agent_results: Optional[List[AgentResult]] = None,
        degraded: Optional[List[str]] = None,
        error: Optional[str] = None,
    ) -> InvestigationEvent:
        """Add one event and wake every follower.

        `seq` is assigned here and nowhere else, from the journal's own length,
        so the sequence is contiguous by construction rather than by a counter
        someone has to remember to increment.
        """
        event = InvestigationEvent(
            seq=len(self._events) + 1,
            case_id=self.case_id,
            kind=kind,
            at=utc_now_iso(),
            status=status if status is not None else self.state.status,
            node=node,
            plan=plan or [],
            nodes_done=self._nodes_done,
            agent_results=agent_results or [],
            degraded=degraded or [],
            error=error,
        )
        self._events.append(event)
        # Set the current bell to release anyone waiting on it, then install a
        # fresh one. A follower captures the bell *before* draining the journal,
        # so an event appended during its drain still wakes it.
        self._bell.set()
        self._bell = asyncio.Event()
        return event

    async def follow(
        self, after: int = 0, *, keepalive_s: float = KEEPALIVE_S
    ) -> AsyncIterator[Optional[InvestigationEvent]]:
        """Yield every event after sequence `after`, then live ones, then stop.

        `None` is yielded when nothing has happened for `keepalive_s`; the route
        turns that into an SSE comment line. A comment has no id, so it cannot
        be replayed on reconnect — which is exactly why the idle signal is one.
        """
        index = max(0, min(after, len(self._events)))
        while True:
            bell = self._bell
            while index < len(self._events):
                yield self._events[index]
                index += 1
            if self.finished:
                return
            try:
                await asyncio.wait_for(bell.wait(), timeout=keepalive_s)
            except asyncio.TimeoutError:
                yield None

    # -- execution ---------------------------------------------------------

    def _deltas(self, update: Dict[str, Any]) -> Tuple[List[AgentResult], List[str]]:
        """What *this node* added, as opposed to what the state now holds.

        The graph's nodes return whole lists (`[*state.agent_results, *new]`),
        so an event carrying the update verbatim would re-send every earlier
        tier's results and a reconnecting client would count them twice. The
        counters here are the difference between an event stream a client can
        append and one it has to diff.
        """
        results: List[AgentResult] = []
        raw_results = update.get("agent_results")
        if isinstance(raw_results, list) and len(raw_results) > self._agents_seen:
            for entry in raw_results[self._agents_seen:]:
                results.append(
                    entry if isinstance(entry, AgentResult) else AgentResult.model_validate(entry)
                )
            self._agents_seen = len(raw_results)

        tags: List[str] = []
        raw_tags = update.get("degraded")
        if isinstance(raw_tags, list) and len(raw_tags) > self._degraded_seen:
            tags = [str(t) for t in raw_tags[self._degraded_seen:]]
            self._degraded_seen = len(raw_tags)

        return results, tags

    def note_node(self, node: str, update: Dict[str, Any], state: Optional[InvestigationState]) -> None:
        """Record one completed graph node."""
        if state is not None:
            self.state = state
        self._nodes_done += 1
        results, tags = self._deltas(update)
        self.append(
            InvestigationEventKind.NODE_COMPLETE,
            node=node,
            agent_results=results,
            degraded=tags,
        )

    def finish(self) -> None:
        if self.finished_monotonic is None:
            self.finished_monotonic = time.monotonic()
        self._bell.set()
        self._bell = asyncio.Event()


class InvestigationRunner:
    """The process's live investigations.

    One instance, module-level. Keyed by `(org_id, case_id)` rather than by
    case id alone: case ids are unique per organisation by design (1.5 chose
    that deliberately, so two tenants minting the same id are two unrelated
    cases), and a registry keyed on the id alone would quietly reintroduce the
    collision the store refuses to have.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        retain_s: float = RETAIN_S,
        max_runs: int = MAX_RUNS,
    ) -> None:
        self._runs: Dict[Tuple[str, str], Run] = {}
        self._session_factory = session_factory
        self._retain_s = retain_s
        self._max_runs = max_runs

    # -- lifecycle ---------------------------------------------------------

    def start(self, state: InvestigationState, org_id: str) -> Run:
        """Accept an investigation and begin running it. Returns immediately.

        The `accepted` event carries the whole node plan, which is what lets a
        client render real progress: it knows the denominator before the first
        node finishes, and every later event is an observed completion rather
        than a guess about how far along things are.
        """
        self._evict()
        run = Run(state, org_id)
        run.append(
            InvestigationEventKind.ACCEPTED,
            status=InvestigationStatus.QUEUED,
            plan=run.plan,
        )
        self._runs[(org_id, state.case_id)] = run
        run.task = asyncio.create_task(self._drive(run))
        return run

    def get(self, org_id: str, case_id: str) -> Optional[Run]:
        return self._runs.get((org_id, case_id))

    async def cancel(self, org_id: str, case_id: str) -> bool:
        """Stop a run that is still going. Returns whether there was one.

        Used by erasure: deleting a case whose graph is still running has to
        stop the graph first, or the run finishes afterwards and writes the rows
        back — an erasure that undoes itself a few seconds later.
        """
        run = self._runs.get((org_id, case_id))
        if run is None or run.task is None or run.finished:
            return False
        run.task.cancel()
        # `asyncio.wait` rather than `await run.task`: awaiting a task that was
        # just cancelled re-raises the CancelledError into *this* coroutine,
        # which would propagate a cancellation the caller never asked for. This
        # form waits for the task to finish unwinding and swallows nothing it
        # should not — a task that failed on the way out has already recorded
        # why on its own journal.
        await asyncio.wait({run.task})
        return True

    def forget(self, org_id: str, case_id: str) -> None:
        """Drop a run's journal. Called after erasure, so a deleted case leaves
        nothing behind in memory either."""
        self._runs.pop((org_id, case_id), None)

    # -- internals ---------------------------------------------------------

    async def _drive(self, run: Run) -> None:
        """Run the graph, journalling each node, then persist and close out."""
        try:
            async for update in investigate_stream(run.state):
                run.note_node(update.node, dict(update.update), update.state)
        except asyncio.CancelledError:
            run.state = run.state.model_copy(
                update={"status": InvestigationStatus.CANCELLED}
            )
            run.append(
                InvestigationEventKind.CANCELLED,
                status=InvestigationStatus.CANCELLED,
            )
            run.finish()
            # Deliberately not persisted: the only caller is erasure, which is
            # about to delete the record anyway, and writing a CANCELLED row on
            # the way out would be a row the delete then has to race.
            raise
        except Exception as exc:
            # FAILED is the orchestrator itself being unable to run, which is
            # rare and different from every agent erroring — the graph's own
            # `finish` node documents that distinction and returns COMPLETE for
            # the latter. Reaching here means the graph did not.
            detail = f"{type(exc).__name__}: {exc}"[:400]
            run.state = run.state.model_copy(
                update={
                    "status": InvestigationStatus.FAILED,
                    "completed_at": utc_now_iso(),
                    "degraded": [*run.state.degraded, "orchestrator:failed"],
                }
            )
            saved = await self._persist(run)
            run.append(
                InvestigationEventKind.FAILED,
                status=InvestigationStatus.FAILED,
                degraded=["orchestrator:failed"] + ([] if saved else [WRITE_FAILED]),
                error=detail,
            )
            run.finish()
            return

        # Persist *before* the terminal event, so a failed write is something
        # the stream can still report. Emitting COMPLETE first and discovering
        # the write failed afterwards would mean the client already believes the
        # case is filed.
        saved = await self._persist(run)
        if not saved:
            run.state = run.state.model_copy(
                update={"degraded": [*run.state.degraded, WRITE_FAILED]}
            )
        run.append(
            InvestigationEventKind.COMPLETE,
            status=run.state.status,
            degraded=[] if saved else [WRITE_FAILED],
        )
        run.finish()

    async def _persist(self, run: Run) -> bool:
        """Save the finished state. False if it could not be written.

        Off the event loop: `EvidenceStore` is synchronous SQLAlchemy, and a
        save that rewrites a case's child rows is long enough that doing it
        inline would stall every other request on this worker.
        """
        return await asyncio.to_thread(self._save, run.org_id, run.state)

    def _save(self, org_id: str, state: InvestigationState) -> bool:
        db = self._session_factory()
        try:
            EvidenceStore(db, org_id).save(state)
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def _evict(self) -> None:
        """Drop journals that are finished and old, oldest first.

        A running investigation is never evicted, whatever the count: dropping
        one would orphan a task that is still writing to it.
        """
        now = time.monotonic()
        stale = [
            key
            for key, run in self._runs.items()
            if run.finished_monotonic is not None
            and now - run.finished_monotonic > self._retain_s
        ]
        for key in stale:
            self._runs.pop(key, None)

        if len(self._runs) <= self._max_runs:
            return
        finished = sorted(
            (r for r in self._runs.values() if r.finished_monotonic is not None),
            key=lambda r: r.finished_monotonic or 0.0,
        )
        for run in finished[: len(self._runs) - self._max_runs]:
            self._runs.pop((run.org_id, run.case_id), None)


#: The process's runner. One per process, like the session registry in
#: `engine/session.py` — and, like it, in-memory until 1.8.
runner = InvestigationRunner()


__all__ = [
    "KEEPALIVE_S",
    "MAX_RUNS",
    "RETAIN_S",
    "WRITE_FAILED",
    "InvestigationRunner",
    "Run",
    "runner",
]
