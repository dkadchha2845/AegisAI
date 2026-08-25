"""
Choosing where an investigation runs — task 1.8.

    .venv/bin/python -m pytest services/api/tests/test_jobs_dispatch.py -q

Three separable decisions, tested apart because they fail apart:

* **Is there a queue?** `broker.available()` — cached, bounded, never raising,
  and False for a switched-off queue as well as an unreachable one.
* **Which queue?** `routing.queue_for()` — the cost class, from metadata that is
  explicitly untrusted, which is why the test for it is also where that
  limitation is pinned.
* **What happens when the answer is no?** The submission must still be answered,
  in this process, with the reduction named. That is invariant 4, and it is the
  one thing here that a citizen would notice.

None of these needs a broker: the decisions are what is under test, not Redis.
`test_jobs_journal.py` and `test_jobs_worker.py` are the ones that need one.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import pytest
from fastapi.testclient import TestClient

from schema.models import (
    EvidenceItem,
    InvestigationEventKind,
    InvestigationState,
    InvestigationStatus,
    utc_now_iso,
)
from services.api.config import settings
from services.api.investigations.runner import InvestigationRunner
from services.api.jobs import broker, routing
from services.api.main import app
from services.worker.celery_app import FAST, QUEUE_PURPOSE, QUEUES, SANDBOX, SLOW, build_app


def _state(items: Optional[List[EvidenceItem]] = None) -> InvestigationState:
    return InvestigationState(
        case_id="AEG-DISPATCH01",
        org_id="org-1",
        created_by="t@aegis.local",
        created_at=utc_now_iso(),
        inputs=items if items is not None else [EvidenceItem(id="ev-01", text="pay verify@ybl")],
    )


# --- is there a queue? -----------------------------------------------------


def test_the_queue_being_switched_off_is_not_the_same_as_unreachable() -> None:
    """Both mean "run it here", and the reason string is what tells them apart.

    Collapsing them would make an operator who set AEGIS_QUEUE=0 look at
    /api/health and think their Redis was broken.
    """
    broker.reset_cache()
    ok, reason = broker.available()
    assert ok is False
    assert "disabled" in reason


def test_the_probe_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is on the request path. Four network round trips per submission is a
    self-inflicted outage, which is the same argument `stores/probe.py` makes."""
    calls = {"n": 0}

    def _counted() -> tuple[bool, str]:
        calls["n"] += 1
        return True, "PONG"

    monkeypatch.setattr(broker, "probe", _counted)
    monkeypatch.setattr(broker, "settings", settings.model_copy(update={"queue_enabled": True}))
    broker.reset_cache()
    try:
        for _ in range(5):
            assert broker.available() == (True, "PONG")
        assert calls["n"] == 1
    finally:
        broker.reset_cache()


def test_an_unreachable_broker_answers_false_rather_than_raising() -> None:
    """A probe failure is information, not an error."""
    broker.reset_cache()
    unreachable = settings.model_copy(
        update={"queue_enabled": True, "redis_url": "redis://127.0.0.1:6399/0"}
    )
    import services.api.jobs.broker as broker_mod

    original = broker_mod.settings
    broker_mod.settings = unreachable
    try:
        ok, reason = broker.available(force=True)
        assert ok is False
        assert "Error" in reason or "error" in reason
    finally:
        broker_mod.settings = original
        broker.reset_cache()


def test_a_broker_url_with_a_password_is_never_echoed() -> None:
    """/api/health prints this. "Secrets: environment only" is worth nothing if
    the status endpoint hands them back out."""
    shown = broker.describe("redis://someone:hunter2@redis.internal:6379/3")
    assert "hunter2" not in shown
    assert "someone" not in shown
    assert shown == "redis://redis.internal:6379/3"


def test_the_url_is_derived_from_host_and_port_when_unset() -> None:
    """So the compose stack needs no variable that does not already exist."""
    import services.api.jobs.broker as broker_mod

    original = broker_mod.settings
    broker_mod.settings = settings.model_copy(
        update={"redis_url": None, "redis_host": "10.1.2.3", "redis_port": 6380, "redis_db": 4}
    )
    try:
        assert broker.redis_url() == "redis://10.1.2.3:6380/4"
    finally:
        broker_mod.settings = original


# --- which queue? ----------------------------------------------------------


@pytest.mark.parametrize(
    "item,expected",
    [
        (EvidenceItem(id="1", text="URGENT: your KYC is suspended"), FAST),
        (EvidenceItem(id="1", filename="notice.png", declared_type="image/png"), FAST),
        (EvidenceItem(id="1", filename="call.mp3"), SLOW),
        (EvidenceItem(id="1", declared_type="video/mp4"), SLOW),
        (EvidenceItem(id="1", filename="bank.apk"), SANDBOX),
        (EvidenceItem(id="1", declared_type="application/vnd.android.package-archive"), SANDBOX),
    ],
)
def test_each_cost_class_routes_where_it_belongs(item: EvidenceItem, expected: str) -> None:
    assert routing.queue_for(_state([item])) == expected


def test_the_most_expensive_artefact_decides_the_whole_submission() -> None:
    """The graph runs once over everything and takes as long as its slowest
    part, so a screenshot submitted alongside an APK is an APK submission for
    scheduling purposes."""
    mixed = [
        EvidenceItem(id="1", text="have a look at this"),
        EvidenceItem(id="2", filename="clip.mp4"),
        EvidenceItem(id="3", filename="bank.apk"),
    ]
    assert routing.queue_for(_state(mixed)) == SANDBOX


def test_an_unlabelled_submission_takes_the_cheap_queue() -> None:
    """Which is the honest default: nothing is known about it yet."""
    assert routing.queue_for(_state([EvidenceItem(id="1")])) == FAST
    assert routing.queue_for(_state([])) == FAST


def test_the_cost_class_is_a_hint_and_a_renamed_apk_proves_it() -> None:
    """Pinning the limitation, not the behaviour — read before task 2.8.

    `EvidenceItem.kind` is UNKNOWN at dispatch; the magic-byte sniff runs on the
    graph's classifier node, which is on the far side of this decision. So an
    APK renamed `photo.jpg` routes to `fast`. That is fine for *scheduling* and
    it is not a security boundary, and 2.8 must enforce isolation where the
    sniffed type is known rather than trusting this.
    """
    renamed = EvidenceItem(id="1", filename="photo.jpg", declared_type="image/jpeg")
    assert routing.queue_for(_state([renamed])) == FAST


def test_every_route_names_a_queue_a_worker_actually_consumes() -> None:
    """A routing table naming a queue nothing is subscribed to is a job that
    silently never runs."""
    configured = {q.name for q in build_app().conf.task_queues}
    assert configured == set(QUEUES)
    for name, route in build_app().conf.task_routes.items():
        assert route["queue"] in configured, name
    for state in (
        _state([EvidenceItem(id="1", text="x")]),
        _state([EvidenceItem(id="1", filename="a.mp4")]),
        _state([EvidenceItem(id="1", filename="a.apk")]),
    ):
        assert routing.queue_for(state) in configured


def test_every_queue_says_what_it_is_for() -> None:
    """`/api/health` publishes this, and "which queue is my case on and why" is
    not a question that should only be answerable from a README."""
    assert set(QUEUE_PURPOSE) == set(QUEUES)
    assert all(text.strip() for text in QUEUE_PURPOSE.values())


# --- what happens when the answer is no? -----------------------------------


def test_no_queue_means_the_graph_runs_here_and_the_case_is_not_marked_down() -> None:
    """Invariant 4's fallback, and the limit of it.

    The submission is answered and the graph runs in this process. The *case*
    carries no queue tag: where an investigation executed is a property of the
    deployment, and 1.7 already recorded what happens when a tag is raised on
    every case — the field becomes one people ignore.
    """
    async def scenario() -> tuple[bool, list[str], list[str]]:
        runner = InvestigationRunner()
        run = runner.start(_state(), "org-1")
        assert run.task is not None
        await run.task
        events = run.events
        return run.queued, list(run.state.degraded), [e.kind.value for e in events]

    queued, degraded, kinds = asyncio.run(scenario())
    assert queued is False
    assert not [tag for tag in degraded if tag.startswith("queue:")]
    assert kinds[0] == InvestigationEventKind.ACCEPTED.value
    assert kinds[-1] == InvestigationEventKind.COMPLETE.value


def test_the_submitting_client_is_told_where_its_case_will_run() -> None:
    """The 202 is the one place `queue:in_process` appears, because it is the
    one place the fact is about this submission rather than about the server."""
    with TestClient(app, client=("10.9.0.1", 51000)) as client:
        response = client.post("/api/investigations", json={"text": "pay verify@ybl now"})
    assert response.status_code == 202
    assert broker.IN_PROCESS in response.json()["degraded"]


def test_a_broker_that_accepts_a_ping_then_refuses_the_job_degrades_the_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """*This* one does go on the case: the queue was reachable, this submission
    was supposed to go to a worker, and it did not."""
    monkeypatch.setattr(broker, "available", lambda **_: (True, "PONG"))
    monkeypatch.setattr(InvestigationRunner, "_enqueue", lambda self, run: False)

    async def scenario() -> tuple[bool, list[str], InvestigationStatus]:
        runner = InvestigationRunner()
        run = runner.start(_state(), "org-1")
        assert run.task is not None
        await run.task
        return run.queued, list(run.state.degraded), run.state.status

    queued, degraded, status = asyncio.run(scenario())
    assert queued is False
    assert broker.UNAVAILABLE in degraded
    # And it still answered, which is the half of invariant 4 that matters most.
    assert status is InvestigationStatus.COMPLETE


def test_a_broker_that_dies_after_the_probe_still_answers_the_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window the ten-second probe cache opens, closed.

    "Reachable" is a fact about the recent past. A broker that goes away between
    the probe and the first journal write would otherwise raise out of
    `set_state`, and a submission would 500 — the exact failure invariant 4
    exists to prevent, arriving through the machinery built to honour it.
    """
    monkeypatch.setattr(broker, "available", lambda **_: (True, "PONG"))

    def _dead(*_a: object, **_k: object) -> object:
        raise ConnectionError("Error 61 connecting to 127.0.0.1:6379. Connection refused.")

    monkeypatch.setattr(broker, "client", _dead)

    async def scenario() -> tuple[bool, list[str], InvestigationStatus]:
        runner = InvestigationRunner()
        run = runner.start(_state(), "org-1")
        assert run.task is not None
        await run.task
        return run.queued, list(run.state.degraded), run.state.status

    queued, degraded, status = asyncio.run(scenario())
    assert queued is False
    assert broker.UNAVAILABLE in degraded
    assert status is InvestigationStatus.COMPLETE


def test_health_reports_where_investigations_run() -> None:
    execution = TestClient(app).get("/api/health").json()["execution"]
    assert execution["mode"] in {"worker", "in-process"}
    assert execution["queue_enabled"] is False        # pinned off for the suite
    assert execution["mode"] == "in-process"
    assert set(execution["queues"]) == set(QUEUES)
    # Nothing was asked for, so nothing is degraded — the same principle
    # `stores/probe.degraded_tags()` applies to an absent Postgres.
    assert execution["degraded"] == []
    assert "@" not in execution["broker"]
