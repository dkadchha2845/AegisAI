"""
The Celery application — task 1.8.

**Why it exists.** Task 1.6 wrote down its own limitation and named this task as
the fix: the graph runs "in this process, on the event loop that serves
requests", so a restart loses every in-flight run and a genuinely slow agent
occupies a worker slot. Phase 2 makes that untenable rather than untidy — APK
static analysis (2.8) is minutes in a sandboxed container and video keyframing
(5.4) is minutes of CPU. Neither can share a lifetime with an HTTP request.

**What it consumes.** `jobs.broker.redis_url()`, so the API and the worker
cannot be pointed at different brokers by configuration drift.

**What it outputs.** A configured `Celery` app with three queues, a retry
policy, and the acknowledgement settings that make "worker crash loses no work"
true rather than hoped for.

**How it connects.** `services/worker/tasks.py` registers tasks on it;
`investigations/runner.py` sends to it; `/api/health` inspects it.

**How it is evaluated.** `test_jobs_queue.py` asserts the three queues exist,
that each task is routed to the queue its cost class names, and that the four
crash-safety settings are what they have to be — a configuration test, because
configuration is the entire mechanism here and a silent default change would
otherwise only surface as lost work in production.

**Limitations, stated.** There is no `sandbox` isolation yet beyond the queue
name. The queue is a routing boundary today; the network-less, read-only
container that makes it a *security* boundary is 2.8's, and until 2.8 exists
nothing runs on that queue except the probe below. Saying "sandbox" of a plain
worker process would be the kind of claim invariant 7 forbids, so it is said
here instead: this is a cost class, and 2.8 makes it a boundary.

Why acks_late is the whole answer to "a worker crash loses no work"
-------------------------------------------------------------------
Celery acknowledges a message when it is *received* by default, so a worker that
dies mid-task has already told the broker the job is handled and the job is
gone. `task_acks_late` moves the acknowledgement to after the task returns,
`task_reject_on_worker_lost` requeues rather than marks-failed when the process
disappears, and `worker_prefetch_multiplier = 1` stops a worker holding a
backlog of messages it has not started and would take down with it. The three
are one decision; changing any of them alone reintroduces the loss.
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from services.api.config import settings
from services.api.jobs import broker

#: Queues by cost class, in the order a reader should think about them.
#: The names are the contract `task_routes` and the worker command line share.
FAST = "fast"
SLOW = "slow"
SANDBOX = "sandbox"
QUEUES = (FAST, SLOW, SANDBOX)

#: What each queue is for. Reported on `/api/health` so the answer to "which
#: queue is my case on and why" does not live only in a README.
QUEUE_PURPOSE = {
    FAST: "investigations over text, URLs and images; retries; cache warms — seconds",
    SLOW: "audio, video and batch re-scoring — minutes",
    SANDBOX: "APK static analysis (task 2.8) — minutes, isolated, never executed",
}


def build_app() -> Celery:
    """The configured app.

    A function rather than module-level statements so a test can build a second
    one against a different broker without reimporting the module, and so the
    URL is read at call time — `settings` is frozen, but the tests that pin the
    routing table should not have to care when it was read.
    """
    url = broker.redis_url()
    # `include` rather than `autodiscover_tasks`: autodiscovery walks a list of
    # app packages looking for a `tasks` module, which is a convention this repo
    # does not follow. Naming the module is one line and cannot silently find
    # nothing — a worker that starts with no tasks registered accepts messages
    # and answers "unregistered task", which looks like a routing bug for the
    # rest of the afternoon.
    app = Celery("aegis", broker=url, backend=url, include=["services.worker.tasks"])
    app.conf.update(
        # --- serialisation ------------------------------------------------
        # JSON only. Celery's historical default was pickle, and a broker that
        # deserialises pickle is remote code execution for anyone who can write
        # to it. The payloads here are Pydantic models, which serialise to JSON
        # by construction.
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # --- crash safety: the three settings that are one decision ---------
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        # --- retry policy ---------------------------------------------------
        # Bounded and backed off. The graph already retries individual agents
        # and returns COMPLETE with a degraded tag, so a task that raises is the
        # orchestrator itself failing — which repeats, and is worth a couple of
        # attempts rather than a dozen.
        task_default_retry_delay=5,
        task_annotations={"*": {"max_retries": settings.queue_max_retries}},
        # --- queues -----------------------------------------------------------
        task_queues=tuple(Queue(name) for name in QUEUES),
        task_default_queue=FAST,
        # The default for each task. `aegis.investigate` is the cheap case and
        # says so here; a submission carrying an APK or a video overrides it per
        # message from `jobs/routing.queue_for()`, because the cost class is a
        # property of the evidence rather than of the task.
        task_routes={
            "aegis.investigate": {"queue": FAST},
            "aegis.sandbox.probe": {"queue": SANDBOX},
        },
        # --- results ----------------------------------------------------------
        # The authoritative result of an investigation is the row `EvidenceStore`
        # writes, not a Celery result: a result backend that expires in an hour
        # is not where a case file belongs, and `run_investigation` therefore
        # ignores its own result. The backend is kept for task *state* — what
        # the probe returned, whether a job is still running — which is what
        # `/api/health` and the dead-letter inspector read.
        result_expires=3600,
        # --- visibility ---------------------------------------------------
        task_track_started=True,
        broker_connection_retry_on_startup=True,
        broker_transport_options={
            # A submission must not hang on a broker that stopped answering
            # mid-connection; the API degrades to in-process instead.
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            # The fourth crash-safety setting, and the one that decides whether
            # "loses no work" means minutes or an hour. `acks_late` leaves a
            # killed worker's message unacknowledged; this is how long the
            # broker waits before offering it to somebody else. Celery's Redis
            # default is 3600 s, which is not a redelivery anyone waits for.
            # See `settings.queue_visibility_timeout_s` for why it must stay
            # longer than the slowest task rather than as short as possible.
            "visibility_timeout": settings.queue_visibility_timeout_s,
        },
    )
    return app


app = build_app()

__all__ = ["FAST", "QUEUES", "QUEUE_PURPOSE", "SANDBOX", "SLOW", "app", "build_app"]
