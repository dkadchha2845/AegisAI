"""
The progress journal, in memory and in Redis — task 1.8.

    .venv/bin/python -m pytest services/api/tests/test_jobs_journal.py -q

1.8 moves the journal off the API process's heap so a Celery worker can write
it and any API replica can read it. The risk in that move is not that Redis
fails; it is that the two implementations quietly differ, and the SSE contract
1.6 was ticked on — resume from `Last-Event-ID`, no duplicates, keepalives that
carry no id — holds for one of them and not the other.

So the conformance tests below are **parametrised over both backends**. A
behaviour that is true in memory and not in Redis is a failure here rather than
a discovery in 1.9. Where an implementation genuinely differs (TTL, visibility
across clients) it gets its own test underneath, and those skip without a
broker — which the run's summary line prints, per task 1.7b.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import List, Optional

import pytest

from schema.models import (
    InvestigationEvent,
    InvestigationEventKind,
    InvestigationState,
    InvestigationStatus,
    utc_now_iso,
)
from services.api.jobs import broker
from services.api.jobs.journal import (
    DLQ_KEY,
    MemoryJournal,
    RedisJournal,
    dead_letter,
    dead_letters,
)

BROKER_OK, BROKER_WHY = broker.probe()
needs_redis = pytest.mark.skipif(
    not BROKER_OK, reason=f"no Redis broker at {broker.describe()}: {BROKER_WHY}"
)


def _state(case_id: str = "AEG-TEST") -> InvestigationState:
    return InvestigationState(
        case_id=case_id,
        org_id="org-jobs",
        created_by="t@aegis.local",
        created_at=utc_now_iso(),
    )


def _event(seq: int, kind: InvestigationEventKind = InvestigationEventKind.NODE_COMPLETE,
           node: Optional[str] = None) -> InvestigationEvent:
    return InvestigationEvent(
        seq=seq,
        case_id="AEG-TEST",
        kind=kind,
        at=utc_now_iso(),
        status=InvestigationStatus.RUNNING,
        node=node or f"node_{seq}",
    )


@pytest.fixture(params=["memory", "redis"])
def journal(request: pytest.FixtureRequest):
    """One journal of each kind, so every test below runs twice."""
    if request.param == "memory":
        yield MemoryJournal()
        return
    if not BROKER_OK:
        pytest.skip(f"no Redis broker at {broker.describe()}: {BROKER_WHY}")
    # A fresh case id per test, so a rerun never inherits a previous run's list
    # and two tests never share a key.
    case_id = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    j = RedisJournal("org-jobs", case_id, retain_s=60)
    try:
        yield j
    finally:
        j.forget()


# --- conformance: both backends -------------------------------------------


def test_an_empty_journal_is_not_finished(journal) -> None:
    assert journal.events() == []
    assert journal.finished() is False
    assert journal.state() is None


def test_events_come_back_in_order(journal) -> None:
    for seq in range(1, 6):
        journal.append(_event(seq))
    assert [e.seq for e in journal.events()] == [1, 2, 3, 4, 5]
    assert [e.node for e in journal.events()] == [f"node_{n}" for n in range(1, 6)]


def test_finished_is_the_last_event_being_terminal(journal) -> None:
    journal.append(_event(1))
    assert journal.finished() is False
    journal.append(_event(2, InvestigationEventKind.COMPLETE))
    assert journal.finished() is True


@pytest.mark.parametrize(
    "kind",
    [
        InvestigationEventKind.COMPLETE,
        InvestigationEventKind.FAILED,
        InvestigationEventKind.CANCELLED,
    ],
)
def test_every_terminal_kind_ends_the_stream(journal, kind) -> None:
    """All three, because a stream that only stops on COMPLETE hangs forever on
    the two paths where something went wrong — which are the paths a client most
    needs to be told about."""
    journal.append(_event(1, kind))
    assert journal.finished() is True


def test_the_state_snapshot_round_trips(journal) -> None:
    """`GET /{id}` reads this. A snapshot that does not survive serialisation is
    a case that reports QUEUED while its stream is on node six."""
    state = _state().model_copy(update={"status": InvestigationStatus.RUNNING})
    journal.set_state(state)
    back = journal.state()
    assert back is not None
    assert back.case_id == state.case_id
    assert back.status is InvestigationStatus.RUNNING


def test_a_follower_replays_a_finished_journal_whole(journal) -> None:
    for seq in range(1, 4):
        journal.append(_event(seq))
    journal.append(_event(4, InvestigationEventKind.COMPLETE))

    seen = asyncio.run(_drain(journal, after=0))
    assert [e.seq for e in seen if e is not None] == [1, 2, 3, 4]


def test_a_follower_resuming_from_an_index_sees_no_duplicate(journal) -> None:
    """The 1.6 reconnect contract, asserted against both backends.

    `Last-Event-ID: 2` means "I have 1 and 2". Off by one here is a client that
    either counts an agent result twice or never sees it, and neither is
    recoverable at the UI.
    """
    for seq in range(1, 4):
        journal.append(_event(seq))
    journal.append(_event(4, InvestigationEventKind.COMPLETE))

    seen = asyncio.run(_drain(journal, after=2))
    assert [e.seq for e in seen if e is not None] == [3, 4]


def test_a_follower_resuming_past_the_end_gets_nothing_and_stops(journal) -> None:
    journal.append(_event(1, InvestigationEventKind.COMPLETE))
    assert asyncio.run(_drain(journal, after=9)) == []


def test_a_live_event_reaches_a_waiting_follower(journal) -> None:
    """The wakeup path — an `asyncio.Event` in memory, a pub/sub channel in
    Redis. This is the half that a replayed-journal test cannot reach, and the
    half where the two implementations are least alike."""

    async def scenario() -> List[Optional[InvestigationEvent]]:
        collected: List[Optional[InvestigationEvent]] = []

        async def follow() -> None:
            async for event in journal.follow(0, keepalive_s=5.0):
                collected.append(event)

        task = asyncio.create_task(follow())
        await asyncio.sleep(0.25)
        journal.append(_event(1))
        await asyncio.sleep(0.25)
        journal.append(_event(2, InvestigationEventKind.COMPLETE))
        await asyncio.wait_for(task, timeout=10)
        return collected

    seen = asyncio.run(scenario())
    assert [e.seq for e in seen if e is not None] == [1, 2]


def test_an_idle_follower_gets_a_keepalive_and_not_an_event(journal) -> None:
    """A keepalive is `None`, which the route turns into an SSE comment. It must
    never be an event: a comment carries no id, and an id is what reconnect
    resumes from."""

    async def scenario() -> List[Optional[InvestigationEvent]]:
        collected: List[Optional[InvestigationEvent]] = []

        async def follow() -> None:
            async for event in journal.follow(0, keepalive_s=0.15):
                collected.append(event)

        task = asyncio.create_task(follow())
        # Long enough that several keepalives must have fired, and nothing has
        # been appended, so everything collected so far can only be keepalives.
        await asyncio.sleep(0.5)
        assert collected and all(e is None for e in collected), collected
        journal.append(_event(1, InvestigationEventKind.COMPLETE))
        await asyncio.wait_for(task, timeout=10)
        return collected

    seen = asyncio.run(scenario())
    assert seen[0] is None, seen
    assert seen[-1] is not None
    assert seen[-1].kind is InvestigationEventKind.COMPLETE


async def _drain(journal, after: int) -> List[Optional[InvestigationEvent]]:
    return [event async for event in journal.follow(after, keepalive_s=0.2)]


# --- Redis only ------------------------------------------------------------


@needs_redis
def test_a_second_process_reads_the_same_journal() -> None:
    """The whole reason 1.8 needed a Redis journal.

    Two `RedisJournal` objects with no shared memory, standing in for the worker
    that writes and the API replica that serves the stream.
    """
    case_id = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    writer = RedisJournal("org-jobs", case_id, retain_s=60)
    reader = RedisJournal("org-jobs", case_id, retain_s=60)
    try:
        writer.set_state(_state(case_id))
        writer.append(_event(1))
        writer.append(_event(2, InvestigationEventKind.COMPLETE))

        assert [e.seq for e in reader.events()] == [1, 2]
        assert reader.finished() is True
        got = reader.state()
        assert got is not None and got.case_id == case_id
    finally:
        writer.forget()


@needs_redis
def test_two_tenants_minting_the_same_case_id_do_not_collide() -> None:
    """1.5 chose case ids unique *per organisation*. A journal keyed on the id
    alone would reintroduce the collision the evidence store refuses to have."""
    case_id = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    a = RedisJournal("org-a", case_id, retain_s=60)
    b = RedisJournal("org-b", case_id, retain_s=60)
    try:
        a.append(_event(1, node="a_only"))
        assert [e.node for e in a.events()] == ["a_only"]
        assert b.events() == []
    finally:
        a.forget()
        b.forget()


@needs_redis
def test_forget_leaves_nothing_behind() -> None:
    """GDPR erasure deletes the rows and the blobs; it has to delete this too."""
    case_id = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    j = RedisJournal("org-jobs", case_id, retain_s=60)
    j.set_state(_state(case_id))
    j.append(_event(1))
    assert j.exists() is True

    j.forget()
    assert j.exists() is False
    assert j.events() == []
    assert j.state() is None


@needs_redis
def test_a_journal_expires_rather_than_accumulating() -> None:
    """RETAIN_S is a TTL here and an eviction sweep in memory. Same number, same
    intent: the timeline is disposable, the case file is not."""
    case_id = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    j = RedisJournal("org-jobs", case_id, retain_s=60)
    try:
        j.append(_event(1))
        j.set_state(_state(case_id))
        conn = broker.client()
        assert 0 < conn.ttl(j.events_key) <= 60
        assert 0 < conn.ttl(j.state_key) <= 60
    finally:
        j.forget()


# --- the dead-letter list --------------------------------------------------


@needs_redis
def test_a_dead_letter_is_recorded_and_readable() -> None:
    marker = uuid.uuid4().hex
    dead_letter({"task": "aegis.investigate", "case_id": marker, "error": "boom"})
    entries = dead_letters(limit=50)
    assert any(e.get("case_id") == marker for e in entries)
    assert all("at" in e for e in entries)
    broker.client().lrem(DLQ_KEY, 0, next(
        raw for raw in broker.client().lrange(DLQ_KEY, -50, -1) if marker in raw
    ))


def test_dead_lettering_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is called from a Celery failure handler. An exception here would
    replace the real failure with a Redis error, and the real failure is the one
    worth keeping."""
    def _boom(*_a, **_k):
        raise ConnectionError("broker gone")

    monkeypatch.setattr(broker, "client", _boom)
    dead_letter({"task": "x"})       # must not raise
    assert dead_letters() == []      # and must not raise here either
