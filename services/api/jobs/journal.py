"""
One investigation's progress journal, in memory or in Redis — task 1.8.

**Why it exists.** Task 1.6 built the journal as a Python list on the object
running the graph, and wrote down why: keeping the whole journal and having each
follower hold an *index* into it turns SSE reconnect into arithmetic instead of
a promise about timing. That reasoning survives 1.8 exactly. What does not
survive is the *location*: once the graph runs on a Celery worker, the process
appending events and the process serving `GET /{id}/stream` are different
processes, and a list on the heap of one of them is invisible to the other.

So the list becomes an interface with two implementations. `MemoryJournal` is
1.6's behaviour, unchanged, and is what a clean clone with no Redis still uses.
`RedisJournal` is the same journal in a list Redis holds, with a pub/sub channel
in place of the `asyncio.Event` and a TTL in place of the eviction sweep. The
follower's contract — "resume from index N, receive the remainder, no
duplicates" — is identical in both, because in both it is `LRANGE`/slice from
an index rather than a queue that forgets what it handed out.

**What it consumes.** `InvestigationEvent`s from whichever process is running
the graph, and `InvestigationState` snapshots as each node completes.

**What it outputs.** The journal back, in order, to any number of followers.

**How it connects.** `investigations/runner.py` owns a journal per run and picks
the implementation from `broker.available()`. `routes/investigations.py` is
unchanged: it still calls `run.follow()` and reads `run.state`.

**How it is evaluated.** `test_jobs_journal.py` runs the *same* conformance
tests against both implementations, so a behaviour that holds in memory and not
in Redis is a failure rather than a discovery. The Redis half is skipped when no
broker is reachable, and the run says so — see task 1.7b for why that sentence
is printed rather than left implied.

**Limitations, stated.** A `RedisJournal` is readable by any API process, which
is the point, but it is not replicated: `--appendonly yes` in the compose file
means an ungraceful Redis restart can lose the last fsync window of *progress
events*. It cannot lose the investigation — the durable record is the evidence
store row written at submission and rewritten at completion, and a follower that
finds no journal is told to read the final state, which is the same 409 path
1.6 already built for a restarted API. Events are capped at `MAX_EVENTS` per
case so a pathological run cannot grow a list without bound.

Why the state snapshot is stored beside the events and not derived from them
----------------------------------------------------------------------------
`GET /{id}` must not disagree with the stream. 1.6 made that true by reading a
live run's state off the object driving it; across processes there is no such
object, and an event carries only what a node *added*, so accumulating events
would rebuild a state that is a fragment-merge away from the real one — and
would break silently the first time a channel gets a reducer, which is the same
hazard `investigate_stream` documents about reconstructing from `updates`. The
worker writes the whole snapshot under its own key instead. It costs one `SET`
per node and it cannot drift.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, List, Optional, Protocol, runtime_checkable

from schema.models import InvestigationEvent, InvestigationEventKind, InvestigationState

from . import broker

#: How long a follower waits before the stream emits a keepalive. SSE comment
#: lines carry no id, so a keepalive can never be replayed or duplicated — which
#: is why the idle path uses one instead of a synthetic heartbeat event.
KEEPALIVE_S = 15.0

#: Finished journals live this long, so a client that reconnects late is still
#: replayed. Afterwards the per-node timeline is gone and the answer is not: the
#: case is durable in the evidence store. In Redis this is a key TTL; in memory
#: it is the runner's eviction sweep. Same number, so the two behave alike.
RETAIN_S = 30 * 60.0

#: A ceiling on events per case. The graph emits one per node — nine today — so
#: this is four orders of magnitude of headroom, and it exists only so that a
#: pathological run cannot grow a Redis list without bound.
MAX_EVENTS = 10_000

#: The event kinds after which nothing more is appended.
TERMINAL = (
    InvestigationEventKind.COMPLETE,
    InvestigationEventKind.FAILED,
    InvestigationEventKind.CANCELLED,
)


def _key(kind: str, org_id: str, case_id: str) -> str:
    return f"aegis:inv:{kind}:{org_id}:{case_id}"


@runtime_checkable
class Journal(Protocol):
    """What a run's progress journal has to be able to do.

    Deliberately small. Everything the SSE route needs is `events`, `finished`
    and `follow`; everything `GET /{id}` needs is `state`. A wider interface
    would be a wider surface for the two implementations to disagree across.
    """

    def append(self, event: InvestigationEvent) -> None: ...

    def events(self) -> List[InvestigationEvent]: ...

    def finished(self) -> bool: ...

    def state(self) -> Optional[InvestigationState]: ...

    def set_state(self, state: InvestigationState) -> None: ...

    def follow(
        self, after: int = 0, *, keepalive_s: float = KEEPALIVE_S
    ) -> AsyncIterator[Optional[InvestigationEvent]]: ...


# --------------------------------------------------------------------------
# In memory — task 1.6's journal, unchanged in behaviour
# --------------------------------------------------------------------------


class MemoryJournal:
    """The journal on this process's heap. What a clean clone uses.

    The bell is captured by a follower *before* it drains the list, so an event
    appended during the drain still wakes it. Setting the current bell and
    installing a fresh one — rather than clearing one — is what makes that safe
    without a lock.
    """

    def __init__(self) -> None:
        self._events: List[InvestigationEvent] = []
        self._state: Optional[InvestigationState] = None
        self._bell = asyncio.Event()

    def append(self, event: InvestigationEvent) -> None:
        self._events.append(event)
        self._ring()

    def events(self) -> List[InvestigationEvent]:
        return list(self._events)

    def finished(self) -> bool:
        return bool(self._events) and self._events[-1].kind in TERMINAL

    def state(self) -> Optional[InvestigationState]:
        return self._state

    def set_state(self, state: InvestigationState) -> None:
        self._state = state

    def _ring(self) -> None:
        self._bell.set()
        self._bell = asyncio.Event()

    async def follow(
        self, after: int = 0, *, keepalive_s: float = KEEPALIVE_S
    ) -> AsyncIterator[Optional[InvestigationEvent]]:
        index = max(0, min(after, len(self._events)))
        while True:
            bell = self._bell
            while index < len(self._events):
                yield self._events[index]
                index += 1
            if self.finished():
                return
            try:
                await asyncio.wait_for(bell.wait(), timeout=keepalive_s)
            except asyncio.TimeoutError:
                yield None


# --------------------------------------------------------------------------
# In Redis — the same journal, visible to every process
# --------------------------------------------------------------------------


class RedisJournal:
    """The journal in a Redis list, with a channel for wakeups.

    Writes are synchronous because the writer is the Celery worker, which is a
    thread in a prefork process and has no event loop. Reads on the SSE path are
    asynchronous because the API does have one and must not block it. The two
    clients are separate objects for that reason and not by accident.

    `events()` and `state()` are also called from sync FastAPI routes, which run
    in a threadpool; a bounded-timeout Redis round trip there is the same shape
    as the SQLAlchemy calls already in those handlers.
    """

    def __init__(self, org_id: str, case_id: str, *, retain_s: float = RETAIN_S) -> None:
        self.org_id = org_id
        self.case_id = case_id
        self.retain_s = retain_s
        self.events_key = _key("journal", org_id, case_id)
        self.state_key = _key("state", org_id, case_id)
        self.channel = _key("tick", org_id, case_id)
        self._sync: Any = None

    # -- writing (worker side) --------------------------------------------

    @property
    def conn(self) -> Any:
        if self._sync is None:
            self._sync = broker.client()
        return self._sync

    def append(self, event: InvestigationEvent) -> None:
        payload = event.model_dump_json()
        pipe = self.conn.pipeline()
        pipe.rpush(self.events_key, payload)
        pipe.ltrim(self.events_key, -MAX_EVENTS, -1)
        pipe.expire(self.events_key, int(self.retain_s))
        # Published after the append, and carrying the sequence rather than the
        # event: a follower that misses the message still finds the event by
        # LRANGE, and one that receives it does not have to trust the payload.
        pipe.publish(self.channel, str(event.seq))
        pipe.execute()

    def set_state(self, state: InvestigationState) -> None:
        self.conn.set(self.state_key, state.model_dump_json(), ex=int(self.retain_s))

    def forget(self) -> None:
        """Erase the journal. Called by GDPR erasure, which must leave nothing."""
        self.conn.delete(self.events_key, self.state_key)

    # -- reading -----------------------------------------------------------

    def exists(self) -> bool:
        return bool(self.conn.exists(self.events_key))

    def events(self) -> List[InvestigationEvent]:
        return [_parse(raw) for raw in self.conn.lrange(self.events_key, 0, -1)]

    def finished(self) -> bool:
        tail = self.conn.lrange(self.events_key, -1, -1)
        return bool(tail) and _parse(tail[0]).kind in TERMINAL

    def state(self) -> Optional[InvestigationState]:
        raw = self.conn.get(self.state_key)
        if not raw:
            return None
        return InvestigationState.model_validate_json(raw)

    async def follow(
        self, after: int = 0, *, keepalive_s: float = KEEPALIVE_S
    ) -> AsyncIterator[Optional[InvestigationEvent]]:
        conn = broker.async_client()
        pubsub = conn.pubsub()
        # Subscribe *before* the first read. The other order has a window in
        # which an event is appended after the read and before the subscribe,
        # and the follower then waits for a message that already happened —
        # which is the cross-process form of the bug the memory journal avoids
        # by capturing its bell first.
        await pubsub.subscribe(self.channel)
        try:
            index = max(0, after)
            while True:
                batch = await conn.lrange(self.events_key, index, -1)
                for raw in batch:
                    index += 1
                    yield _parse(raw)
                # Asked of the journal, not of what was just yielded. A follower
                # resuming from an index at or past the end of a *finished*
                # journal yields nothing, and deciding "done" from the events
                # this call happened to emit would leave it waiting on a channel
                # that will never carry another message. The memory journal has
                # the same line for the same reason, which is the point of
                # writing them to look alike.
                if await self._finished(conn):
                    return
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=keepalive_s
                )
                if message is None:
                    yield None
        finally:
            try:
                await pubsub.unsubscribe(self.channel)
                await pubsub.aclose()
            finally:
                await conn.aclose()


    async def _finished(self, conn: Any) -> bool:
        """`finished()` over the async client, so the SSE loop never blocks."""
        tail = await conn.lrange(self.events_key, -1, -1)
        return bool(tail) and _parse(tail[0]).kind in TERMINAL


def _parse(raw: str) -> InvestigationEvent:
    return InvestigationEvent.model_validate(json.loads(raw))


# --------------------------------------------------------------------------
# The dead-letter list
# --------------------------------------------------------------------------

#: Where a job goes when the retry policy is exhausted. A list rather than a
#: Celery result: the point of a dead letter is that somebody reads it later,
#: and a result that expires in an hour is not that.
DLQ_KEY = "aegis:inv:dlq"

#: How many dead letters are kept. Oldest dropped first — an operator reading
#: the queue wants the recent failures, and an unbounded list is how a broker
#: with a 256 MB cap starts evicting the journals people are still following.
DLQ_MAX = 500


def dead_letter(entry: dict) -> None:
    """Record a job the retry policy gave up on. Never raises.

    Never raises because it is called from a Celery failure handler: an
    exception here would replace the real failure with a Redis error, and the
    real failure is the one worth keeping.
    """
    try:
        conn = broker.client()
        pipe = conn.pipeline()
        pipe.rpush(DLQ_KEY, json.dumps({"at": time.time(), **entry}))
        pipe.ltrim(DLQ_KEY, -DLQ_MAX, -1)
        pipe.execute()
    except Exception:
        pass


def dead_letters(limit: int = 50) -> List[dict]:
    """The most recent dead letters, newest last. Empty if Redis is unreachable."""
    try:
        conn = broker.client()
        return [json.loads(raw) for raw in conn.lrange(DLQ_KEY, -limit, -1)]
    except Exception:
        return []


__all__ = [
    "DLQ_KEY",
    "DLQ_MAX",
    "KEEPALIVE_S",
    "MAX_EVENTS",
    "RETAIN_S",
    "TERMINAL",
    "Journal",
    "MemoryJournal",
    "RedisJournal",
    "dead_letter",
    "dead_letters",
]
