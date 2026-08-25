"""
The worker side of task 1.8 — configuration, execution, and giving up.

    .venv/bin/python -m pytest services/api/tests/test_jobs_worker.py -q

Two halves, and the split is deliberate.

**Configuration is the mechanism.** "A worker crash loses no work" is not code
anyone wrote; it is four Celery settings, and a silent default change would only
surface as work disappearing in production. So they are asserted by name, with
the reason attached to each.

**Execution is the same code as the in-process path.** `run_investigation` is
thin on purpose — it rebuilds the state, binds a Redis journal, and calls the
same `drive()` the API calls — so what is worth testing here is not the graph
again but the three things only this side has: the journal ends up in Redis, a
redelivery produces one timeline rather than two, and a task that exhausts its
retries is dead-lettered rather than dropped.

The execution half needs a broker and skips without one. The run's summary line
says which happened, per task 1.7b.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

import pytest

from schema.models import (
    EvidenceItem,
    InvestigationEventKind,
    InvestigationState,
    InvestigationStatus,
    utc_now_iso,
)
from services.api.config import settings
from services.api.db import SessionLocal, init_db
from services.api.jobs import broker
from services.api.jobs.journal import DLQ_KEY, RedisJournal, dead_letters
from services.api.stores.evidence import EvidenceStore
from services.worker import tasks as worker_tasks
from services.worker.celery_app import FAST, SANDBOX, build_app

BROKER_OK, BROKER_WHY = broker.probe()
needs_redis = pytest.mark.skipif(
    not BROKER_OK, reason=f"no Redis broker at {broker.describe()}: {BROKER_WHY}"
)

ORG = "org-worker"


@pytest.fixture(autouse=True)
def _db() -> None:
    init_db()


def _write_accepted(journal: RedisJournal, case_id: str) -> None:
    """What `runner.start()` puts in the journal before it sends the message."""
    from schema.models import InvestigationEvent

    journal.append(
        InvestigationEvent(
            seq=1,
            case_id=case_id,
            kind=InvestigationEventKind.ACCEPTED,
            at=utc_now_iso(),
            status=InvestigationStatus.QUEUED,
            plan=["begin", "classify", "finish"],
        )
    )


def _state(case_id: str) -> InvestigationState:
    return InvestigationState(
        case_id=case_id,
        org_id=ORG,
        created_by="t@aegis.local",
        created_at=utc_now_iso(),
        status=InvestigationStatus.QUEUED,
        inputs=[EvidenceItem(id="ev-01", text="URGENT: pay Rs 4999 to refund@okaxis")],
    )


# --- configuration: the four settings that are one decision -----------------


def test_a_job_is_acknowledged_after_it_finishes_not_when_it_is_received() -> None:
    """The default acks on receipt, so a worker that dies mid-task has already
    told the broker the job is handled — and the job is gone."""
    assert build_app().conf.task_acks_late is True


def test_a_lost_worker_requeues_rather_than_marks_failed() -> None:
    """`acks_late` alone leaves a job that outlived its process in limbo."""
    assert build_app().conf.task_reject_on_worker_lost is True


def test_a_worker_does_not_hold_a_backlog_it_has_not_started() -> None:
    """Prefetch is the third part of the same decision: a worker holding ten
    unstarted messages takes all ten down with it."""
    assert build_app().conf.worker_prefetch_multiplier == 1


def test_the_broker_never_deserialises_pickle() -> None:
    """Celery's historical default. A broker that unpickles is remote code
    execution for anyone who can write to it, and everything sent here is a
    Pydantic model, which is JSON by construction."""
    conf = build_app().conf
    assert conf.task_serializer == "json"
    assert conf.accept_content == ["json"]
    assert "pickle" not in conf.accept_content


def test_the_retry_budget_is_bounded_and_configurable() -> None:
    """Unbounded retries on an orchestrator failure is a job that never dies and
    a queue that never drains."""
    annotations = build_app().conf.task_annotations
    assert annotations["*"]["max_retries"] == settings.queue_max_retries
    assert 0 <= settings.queue_max_retries <= 10


def test_the_investigation_task_does_not_store_its_own_result() -> None:
    """The result is the evidence-store row. A second copy that expires in an
    hour is a second thing a reader can trust and be wrong about."""
    assert worker_tasks.run_investigation.ignore_result is True


def test_the_tasks_are_registered_under_the_names_the_api_sends() -> None:
    """A typo here is a job that is accepted and answered with "unregistered
    task", which reads like a routing bug for the rest of the afternoon."""
    app = build_app()
    app.loader.import_default_modules()
    assert "aegis.investigate" in app.tasks
    assert "aegis.sandbox.probe" in app.tasks
    assert app.conf.task_routes["aegis.investigate"]["queue"] == FAST
    assert app.conf.task_routes["aegis.sandbox.probe"]["queue"] == SANDBOX


def test_the_sandbox_probe_is_the_ninety_second_shape_the_task_asks_for() -> None:
    """Task 1.8's first acceptance criterion names a 90-second APK-shaped stub.
    This is it, and the number is the criterion rather than a guess."""
    assert worker_tasks.SANDBOX_PROBE_SECONDS == 90


def test_the_sandbox_probe_executes_nothing() -> None:
    """It is 2.8's placeholder, and 2.8's rule is static analysis only. A probe
    that grew a subprocess call would be the wrong shape to inherit."""
    result = worker_tasks.sandbox_probe(seconds=0)
    assert result["findings"] == []
    assert result["seconds"] == 0
    # The returned shape carries the rule forward to whoever fills it in.
    assert "never execution" in result["note"]


# --- execution --------------------------------------------------------------


@needs_redis
def test_the_task_runs_the_graph_and_journals_it_into_redis() -> None:
    """One event per node, in Redis, plus a durable row — which is the whole of
    "result backend into the evidence store"."""
    case_id = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    state = _state(case_id)
    journal = RedisJournal(ORG, case_id)
    try:
        out = worker_tasks.run_investigation(
            case_id=case_id, org_id=ORG, state_json=state.model_dump_json()
        )
        assert out["status"] == InvestigationStatus.COMPLETE.value

        events = journal.events()
        assert [e.seq for e in events] == list(range(1, len(events) + 1))
        assert events[-1].kind is InvestigationEventKind.COMPLETE
        assert journal.finished() is True

        db = SessionLocal()
        try:
            saved = EvidenceStore(db, ORG).load(case_id)
        finally:
            db.close()
        assert saved is not None
        assert saved.status is InvestigationStatus.COMPLETE
    finally:
        journal.forget()


@needs_redis
def test_a_redelivered_job_produces_one_timeline_and_not_two() -> None:
    """`acks_late` means a job can run twice. Everything a run writes is keyed
    on the case id so a second execution overwrites; the journal is the one
    thing that would otherwise *append*, so the task truncates it back to the
    accepted event first."""
    case_id = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    state = _state(case_id)
    journal = RedisJournal(ORG, case_id)
    try:
        kwargs: Dict[str, Any] = {
            "case_id": case_id,
            "org_id": ORG,
            "state_json": state.model_dump_json(),
        }
        # The submission path's `accepted` event, written by the API before the
        # message is sent. It has to survive a redelivery — a client that
        # reconnects afterwards still needs the node plan off it.
        _write_accepted(journal, case_id)

        worker_tasks.run_investigation(**kwargs)
        first = journal.events()

        worker_tasks.run_investigation(**kwargs)
        second = journal.events()

        assert len(second) == len(first), "a redelivery appended a second timeline"
        assert [e.seq for e in second] == list(range(1, len(second) + 1))
        assert second[0].kind is InvestigationEventKind.ACCEPTED
        assert second[-1].kind is InvestigationEventKind.COMPLETE
    finally:
        journal.forget()


@needs_redis
def test_the_api_can_read_a_journal_the_worker_wrote() -> None:
    """The cross-process claim, end to end through the runner rather than
    through a journal object: `runner.get()` must adopt a case this process
    never started."""
    from services.api.investigations.runner import InvestigationRunner

    case_id = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    state = _state(case_id)
    journal = RedisJournal(ORG, case_id)
    try:
        worker_tasks.run_investigation(
            case_id=case_id, org_id=ORG, state_json=state.model_dump_json()
        )
        import services.api.jobs.broker as broker_mod

        original = broker_mod.settings
        broker_mod.settings = settings.model_copy(update={"queue_enabled": True})
        broker.reset_cache()
        try:
            adopted = InvestigationRunner().get(ORG, case_id)
        finally:
            broker_mod.settings = original
            broker.reset_cache()

        assert adopted is not None, "a case journalled by a worker was not adopted"
        assert adopted.state.case_id == case_id
        assert adopted.state.status is InvestigationStatus.COMPLETE
        assert adopted.finished is True
    finally:
        journal.forget()


@needs_redis
def test_an_unknown_case_is_not_adopted() -> None:
    """The other direction, or `GET /{id}/stream` would hang on a typo instead
    of 404ing on one."""
    import services.api.jobs.broker as broker_mod
    from services.api.investigations.runner import InvestigationRunner

    original = broker_mod.settings
    broker_mod.settings = settings.model_copy(update={"queue_enabled": True})
    broker.reset_cache()
    try:
        assert InvestigationRunner().get(ORG, "AEG-NOSUCHCASE1") is None
    finally:
        broker_mod.settings = original
        broker.reset_cache()


# --- giving up --------------------------------------------------------------


@needs_redis
def test_a_job_that_exhausts_its_retries_is_dead_lettered() -> None:
    """A job simply dropped at that point is work the system silently forgot.

    `on_failure` is called by Celery once the retries are spent; it is invoked
    directly here because the alternative is standing up a worker and killing a
    task three times to observe one list append.
    """
    marker = f"AEG-{uuid.uuid4().hex[:12].upper()}"
    worker_tasks.run_investigation.on_failure(
        RuntimeError("graph exploded"),
        "task-123",
        (),
        {"case_id": marker, "org_id": ORG},
        None,
    )
    entries = dead_letters(limit=50)
    mine = [e for e in entries if e.get("case_id") == marker]
    assert mine, "the failure was not recorded anywhere"
    assert mine[0]["task"] == "aegis.investigate"
    assert "graph exploded" in mine[0]["error"]
    assert mine[0]["org_id"] == ORG

    conn = broker.client()
    for raw in conn.lrange(DLQ_KEY, -50, -1):
        if marker in raw:
            conn.lrem(DLQ_KEY, 0, raw)


@needs_redis
def test_a_job_lands_on_its_own_queue_and_not_on_another() -> None:
    """Routing verified at the transport, because the banner suggests otherwise.

    A Celery worker starting up prints every queue as `exchange=fast(direct)
    key=fast`, which reads like all three are bound to one routing key — i.e.
    like a worker started with `-Q sandbox` alone would receive nothing. It is
    cosmetic: the Redis transport uses the queue name as the list name. This
    asserts the behaviour rather than the banner, because "the sandbox queue is
    a separate queue" is the claim the cost classes rest on.
    """
    app = build_app()
    app.loader.import_default_modules()

    # The routing decision itself, which is deterministic and is what the cost
    # classes rest on.
    assert app.amqp.router.route({"queue": SANDBOX}, "aegis.sandbox.probe")["queue"].name == SANDBOX
    assert app.amqp.router.route({}, "aegis.investigate")["queue"].name == FAST

    # And the same claim at the transport, which is where the banner is
    # misleading. Skipped rather than raced when a worker is up: a consumer
    # takes the message before this can look, and an assertion that passes
    # because something ate the evidence is worse than one that did not run.
    if app.control.ping(timeout=0.4):
        pytest.skip("a worker is consuming these queues; the list length races it")

    conn = broker.client()
    for name in (FAST, SANDBOX):
        conn.delete(name)
    try:
        app.send_task("aegis.sandbox.probe", kwargs={"seconds": 0}, queue=SANDBOX)
        assert conn.llen(SANDBOX) == 1
        assert conn.llen(FAST) == 0, "a sandbox job was published onto the fast queue"
    finally:
        for name in (FAST, SANDBOX):
            conn.delete(name)


def test_a_killed_workers_job_is_redelivered_in_minutes_not_an_hour() -> None:
    """The fourth crash-safety setting, and the easiest to leave at its default.

    `acks_late` leaves a SIGKILLed worker's message unacknowledged, which is what
    makes the job recoverable at all. The visibility timeout is how long the
    broker waits before offering it to somebody else, and Celery's Redis default
    is 3600 seconds — so the guarantee holds and nobody waits for it. It must
    also stay *longer* than the slowest task, or a job that is merely slow gets
    handed to a second worker while the first is still running it.
    """
    timeout = build_app().conf.broker_transport_options["visibility_timeout"]
    assert timeout == settings.queue_visibility_timeout_s
    assert timeout < 3600, "left at Celery's Redis default — an hour to redeliver"
    assert timeout >= 600, "shorter than the sandbox queue's stated budget of minutes"
