"""
Driving one investigation, and saying what it is doing while it does it.

**Why it exists.** Task 1.6's first acceptance criterion is "submit → live
per-node progress → final report, end to end". Three things have to be true at
once for that sentence: the request must return before the graph finishes, the
progress must be *observed* rather than estimated, and a client that drops its
connection must be able to come back without seeing anything twice. This module
is where all three are arranged.

**What it consumes.** An `InvestigationState` that intake has already built,
1.3's `investigate_stream()`, and — since 1.8 — a journal from `jobs/journal.py`
and a verdict from `jobs/broker.available()` on whether there is a worker to
send the graph to.

**What it outputs.** A `Run`: a journal of `InvestigationEvent`s with monotonic
sequence numbers, the freshest state, and a durable save through 1.5's
`EvidenceStore` when the graph finishes.

**How it connects.** `routes/investigations.py` starts a run, follows its
journal for SSE, and reads its state for `GET /{id}`. `services/worker/tasks.py`
calls the same `drive()` on the other side of the queue. Nothing else touches it.

**How it is evaluated.** `test_investigations_api.py`: a run emits one event per
graph node with contiguous sequence numbers, a follower that reconnects with
`Last-Event-ID` receives the remainder and no duplicate, a follower that arrives
after the run finished is replayed the whole journal, a cancelled run stops,
and a store that refuses the write degrades the investigation instead of losing
the answer. `test_jobs_dispatch.py` covers the 1.8 half: which side of the queue
a run lands on, and that an unreachable broker degrades to this process rather
than failing the submission.

**Limitations, stated.** Since 1.8 execution is on a Celery worker *when a
broker is reachable*; with none, it is here, on the event loop that serves
requests, tagged `queue:in_process`. In that mode the three things 1.6 wrote
down are still true and should still be said: a restart loses every in-flight
run (the durable record then says QUEUED forever, because nothing is left to
move it on); the journal is in memory, so a client reconnecting after a restart
gets a 404 on the stream even though `GET /{id}` and the report still work from
the database; and a genuinely slow agent occupies a worker slot. On the queue
path none of the three holds — that is what 1.8 bought — but a broker with no
worker consuming it is a fourth state, and it is reported on `/api/health`
rather than discovered.

Why the journal is a list and not a queue
-----------------------------------------
A queue per subscriber is the usual way to fan out events, and it makes the
reconnect requirement unsatisfiable: once an event has been taken off a queue it
is gone, so a client that dropped between two events has no way to ask for what
it missed, and the server has no way to know whether it should. Keeping the
whole journal and having each follower hold an *index* into it turns reconnect
into arithmetic — `Last-Event-ID: 4` means "resume from index 4" — and makes
"without duplicate events" a property of the data structure rather than a
promise about timing. 1.8 changes where the list lives, from this process's heap
to Redis, and changes nothing about that argument.

Why `drive()` is a function and not a method
--------------------------------------------
It is called from two processes. The API calls it on its own event loop when
there is no queue; the Celery worker calls it under `asyncio.run` when there is.
A method on `InvestigationRunner` would have made the worker construct a runner
— a registry of *live in-process runs* — to execute one job that is not one.
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
from ..jobs import broker
from ..jobs.journal import KEEPALIVE_S, RETAIN_S, Journal, MemoryJournal, RedisJournal
from ..orchestration.graph import investigate_stream, node_plan
from ..stores.evidence import EvidenceStore

#: A ceiling on remembered in-process runs, so a busy process cannot accumulate
#: journals without bound. Oldest finished run goes first; a running one is
#: never evicted. Redis journals expire on their own TTL instead.
MAX_RUNS = 128

#: Recorded on the investigation when the final save fails. The answer still
#: reached the caller over the stream; what was lost is its durability, and the
#: distinction belongs in `degraded` rather than in a 500.
WRITE_FAILED = "store:evidence:write_failed"


class Run:
    """One investigation in flight, plus everything anyone may still ask about it.

    Since 1.8 the journal is injected rather than owned: a `MemoryJournal` for a
    run executing here, a `RedisJournal` for one executing on a worker. Every
    method below is written against the interface, so the route reading
    `run.state` and `run.follow()` cannot tell which it has — which is the point,
    and is why `routes/investigations.py` needed no edit for this task.
    """

    def __init__(
        self,
        state: InvestigationState,
        org_id: str,
        *,
        journal: Optional[Journal] = None,
    ) -> None:
        self.case_id = state.case_id
        self.org_id = org_id
        self.plan: List[str] = node_plan()
        self.started_monotonic = time.monotonic()
        self.finished_monotonic: Optional[float] = None
        self.task: Optional["asyncio.Task[None]"] = None

        #: Whether this run was handed to a worker. Set by the runner, read by
        #: the route so a 202 can tell the client how its case will be executed.
        self.queued = False
        self.journal: Journal = journal if journal is not None else MemoryJournal()
        self.journal.set_state(state)
        self._nodes_done = 0
        self._agents_seen = 0
        self._degraded_seen = 0

    # -- state -------------------------------------------------------------

    @property
    def state(self) -> InvestigationState:
        """The freshest snapshot. Read through the journal so that an API
        process serving `GET /{id}` for a case executing on a worker gets the
        worker's latest node, not the QUEUED row the submission wrote."""
        state = self.journal.state()
        if state is None:  # pragma: no cover - set in __init__ and on every node
            raise RuntimeError(f"run {self.case_id} has no state")
        return state

    @state.setter
    def state(self, value: InvestigationState) -> None:
        self.journal.set_state(value)

    # -- journal -----------------------------------------------------------

    @property
    def events(self) -> List[InvestigationEvent]:
        return self.journal.events()

    @property
    def finished(self) -> bool:
        if self.finished_monotonic is not None:
            return True
        return self.journal.finished()

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
        someone has to remember to increment. There is exactly one writer per
        case — the API appends `accepted` before dispatch and then stops, and the
        worker appends everything after it — so reading a length and writing the
        next index is sequential rather than a race.
        """
        event = InvestigationEvent(
            seq=len(self.journal.events()) + 1,
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
        self.journal.append(event)
        return event

    async def follow(
        self, after: int = 0, *, keepalive_s: float = KEEPALIVE_S
    ) -> AsyncIterator[Optional[InvestigationEvent]]:
        """Yield every event after sequence `after`, then live ones, then stop.

        `None` is yielded when nothing has happened for `keepalive_s`; the route
        turns that into an SSE comment line. A comment has no id, so it cannot
        be replayed on reconnect — which is exactly why the idle signal is one.
        """
        async for event in self.journal.follow(after, keepalive_s=keepalive_s):
            yield event

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


# --------------------------------------------------------------------------
# Executing one investigation — the same code on both sides of the queue
# --------------------------------------------------------------------------


def _save(org_id: str, state: InvestigationState, session_factory: Callable[[], Session]) -> bool:
    db = session_factory()
    try:
        EvidenceStore(db, org_id).save(state)
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


async def _persist(
    run: Run, session_factory: Callable[[], Session]
) -> bool:
    """Save the finished state. False if it could not be written.

    Off the event loop: `EvidenceStore` is synchronous SQLAlchemy, and a save
    that rewrites a case's child rows is long enough that doing it inline would
    stall every other request on this worker.
    """
    return await asyncio.to_thread(_save, run.org_id, run.state, session_factory)


async def drive(
    run: Run, *, session_factory: Callable[[], Session] = SessionLocal
) -> None:
    """Run the graph, journalling each node, then persist and close out.

    The one place an investigation is executed, whichever process is executing
    it. `session_factory` is a parameter because the worker binds its own
    sessions and because the tests substitute a store that refuses to write.
    """
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
        saved = await _persist(run, session_factory)
        run.append(
            InvestigationEventKind.FAILED,
            status=InvestigationStatus.FAILED,
            degraded=["orchestrator:failed"] + ([] if saved else [WRITE_FAILED]),
            error=detail,
        )
        run.finish()
        # Re-raised since 1.8 so the worker's retry policy sees a failure. In
        # the in-process path `_drive` swallows it again, because there is no
        # retry there and an unhandled exception on a background task is a
        # warning on stderr rather than information anyone acts on.
        raise

    # Persist *before* the terminal event, so a failed write is something
    # the stream can still report. Emitting COMPLETE first and discovering
    # the write failed afterwards would mean the client already believes the
    # case is filed.
    saved = await _persist(run, session_factory)
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


class InvestigationRunner:
    """The process's live investigations, and the choice of where to run one.

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

        Where it runs is decided here and nowhere else. A reachable broker means
        a Redis journal and a Celery message; an unreachable or disabled one
        means a memory journal and a task on this event loop, which is 1.6's
        behaviour and is tagged rather than silent.

        The `accepted` event carries the whole node plan, which is what lets a
        client render real progress: it knows the denominator before the first
        node finishes, and every later event is an observed completion rather
        than a guess about how far along things are. It is written *before* the
        message is sent, so a follower that connects in the gap before a worker
        picks the job up already has the plan.
        """
        self._evict()
        queued, _reason = broker.available()

        if queued:
            run = self._start_queued(state, org_id)
            if run is not None:
                return run
            # Everything from here is the fallback: the broker answered PING and
            # then would not take the job — it refused the message, or it died
            # in the window between the probe and the first journal write. The
            # only honest response is the one invariant 4 requires: answer
            # anyway, here, and say what happened. This *is* a per-case
            # degradation and goes on the case, unlike simply having no queue,
            # which is a property of the deployment. See `broker.IN_PROCESS`.
            state = state.model_copy(
                update={"degraded": _with_tag(state.degraded, broker.UNAVAILABLE)}
            )

        run = Run(state, org_id, journal=MemoryJournal())
        self._accept(run)
        run.task = asyncio.create_task(self._drive_locally(run))
        return run

    def _start_queued(self, state: InvestigationState, org_id: str) -> Optional[Run]:
        """Try the worker path. None if any part of it would not work.

        Every Redis touch is inside the try, not just the send. The probe is
        cached for ten seconds, so "reachable" is a fact about the recent past;
        a broker that goes away in that window would otherwise raise out of
        `set_state` and turn a submission into a 500 — which is the failure
        invariant 4 exists to prevent, arriving through the machinery built to
        honour it.
        """
        try:
            journal = RedisJournal(org_id, state.case_id, retain_s=self._retain_s)
            run = Run(state, org_id, journal=journal)
            run.queued = True
            self._accept(run)
            self._runs[(org_id, state.case_id)] = run
            if self._enqueue(run):
                return run
        except Exception as exc:
            print(f"[aegis] queue unusable ({type(exc).__name__}: {exc}); running in process")
        self._runs.pop((org_id, state.case_id), None)
        return None

    def _accept(self, run: Run) -> None:
        """Journal the `accepted` event and remember the run.

        `degraded` is left empty on purpose. An event's degraded list is
        rendered by the UI as "what this step could not do", and execution
        location is not that — see `broker.IN_PROCESS`. The submitting client is
        told on the 202 instead, which is a per-request fact rather than
        something written onto the case's timeline.
        """
        run.append(
            InvestigationEventKind.ACCEPTED,
            status=InvestigationStatus.QUEUED,
            plan=run.plan,
        )
        self._runs[(run.org_id, run.case_id)] = run

    def _enqueue(self, run: Run) -> bool:
        """Send the job to a worker. False if the broker refused it.

        Imported lazily: the API must still boot if Celery is not installed, and
        a `send_task` that raises must degrade rather than 500 a submission.
        """
        try:
            from services.worker.celery_app import app as celery_app

            from ..jobs.routing import queue_for, remember_task

            result = celery_app.send_task(
                "aegis.investigate",
                kwargs={
                    "case_id": run.case_id,
                    "org_id": run.org_id,
                    "state_json": run.state.model_dump_json(),
                },
                queue=queue_for(run.state),
            )
            remember_task(run.org_id, run.case_id, result.id)
            return True
        except Exception as exc:  # broker refused, celery absent, anything
            print(f"[aegis] queue unavailable ({type(exc).__name__}: {exc}); running in process")
            return False

    async def _drive_locally(self, run: Run) -> None:
        """1.6's in-process execution. Swallows what `drive` re-raises.

        A background task that raises produces an "exception was never
        retrieved" warning on stderr and nothing anyone acts on; the failure has
        already been journalled and persisted by `drive` itself, which is the
        part that matters. On the queue path the same exception is what the
        retry policy is watching for, which is why it is re-raised there.
        """
        try:
            await drive(run, session_factory=self._session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    def get(self, org_id: str, case_id: str) -> Optional[Run]:
        """The live run, from this process or from Redis.

        A case dispatched to a worker by *another* API process has no entry in
        this dictionary, and serving a 404 for it would make the stream depend
        on which replica the client's connection landed on. So a missing local
        entry falls through to the shared journal, and a run is reconstructed
        around it for reading.
        """
        run = self._runs.get((org_id, case_id))
        if run is not None:
            return run
        return self._adopt(org_id, case_id)

    def _adopt(self, org_id: str, case_id: str) -> Optional[Run]:
        """Rebuild a read-only view of a run journalled by another process."""
        if not broker.available()[0]:
            return None
        try:
            journal = RedisJournal(org_id, case_id, retain_s=self._retain_s)
            if not journal.exists():
                return None
            state = journal.state()
            if state is None:
                return None
            return Run(state, org_id, journal=journal)
        except Exception:
            return None

    async def cancel(self, org_id: str, case_id: str) -> bool:
        """Stop a run that is still going. Returns whether there was one.

        Used by erasure: deleting a case whose graph is still running has to
        stop the graph first, or the run finishes afterwards and writes the rows
        back — an erasure that undoes itself a few seconds later. That argument
        is why the queue path revokes with `terminate=True` rather than only
        marking the id revoked: a job already executing has to be interrupted,
        not merely prevented from starting.
        """
        run = self._runs.get((org_id, case_id))
        if run is not None and run.task is not None and not run.finished:
            run.task.cancel()
            # `asyncio.wait` rather than `await run.task`: awaiting a task that
            # was just cancelled re-raises the CancelledError into *this*
            # coroutine, which would propagate a cancellation the caller never
            # asked for. This form waits for the task to finish unwinding and
            # swallows nothing it should not — a task that failed on the way out
            # has already recorded why on its own journal.
            await asyncio.wait({run.task})
            return True

        from ..jobs.routing import revoke_task

        return await asyncio.to_thread(revoke_task, org_id, case_id)

    def forget(self, org_id: str, case_id: str) -> None:
        """Drop a run's journal. Called after erasure, so a deleted case leaves
        nothing behind in memory — or in Redis — either."""
        self._runs.pop((org_id, case_id), None)
        try:
            if broker.available()[0]:
                RedisJournal(org_id, case_id).forget()
                from ..jobs.routing import forget_task

                forget_task(org_id, case_id)
        except Exception:
            pass

    # -- internals ---------------------------------------------------------

    def _evict(self) -> None:
        """Drop journals that are finished and old, oldest first.

        A running investigation is never evicted, whatever the count: dropping
        one would orphan a task that is still writing to it. Only in-process
        runs are held here; a Redis journal expires on its own TTL, which is the
        same number for the same reason.
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


def _with_tag(tags: List[str], tag: str) -> List[str]:
    """Append a degradation tag once. Two submissions of the same case must not
    make the same tag appear twice on a list the UI renders."""
    return list(tags) if tag in tags else [*tags, tag]


#: The process's runner. One per process, like the session registry in
#: `engine/session.py` — and, unlike it, no longer the only place a run can be.
runner = InvestigationRunner()


__all__ = [
    "KEEPALIVE_S",
    "MAX_RUNS",
    "RETAIN_S",
    "WRITE_FAILED",
    "InvestigationRunner",
    "Run",
    "drive",
    "runner",
]
