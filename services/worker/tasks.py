"""
What a worker actually runs — task 1.8.

**Why it exists.** `investigations/runner.py` decides *where* an investigation
runs; this is the other side of that decision. It is deliberately thin: the
graph, the journal and the evidence-store write are all `drive()`, shared with
the in-process path, so the two cannot diverge in behaviour and only differ in
which process is executing them.

**What it consumes.** A case id, an org id, and the `InvestigationState` as JSON
— everything needed to rebuild the run, and nothing that only exists in an API
process's memory.

**What it outputs.** Journal events into Redis as each node completes, and the
finished `InvestigationState` into the evidence store. Not into Celery's result
backend: an investigation's result is a case file, and a case file does not
belong in a key that expires in an hour.

**How it connects.** `runner.InvestigationRunner._enqueue` sends
`aegis.investigate`; `jobs/routing.queue_for` picks its queue.

**How it is evaluated.** `test_jobs_worker.py` runs the task in-process against
a real Redis journal and asserts the same properties the in-process path is held
to — one event per node, contiguous sequence numbers, a durable row at the end
— plus the two that only exist here: a failure is dead-lettered after the retry
budget, and a task that is redelivered does not produce a second set of events.

**Limitations, stated.** `asyncio.run` per task: the graph is async and a prefork
Celery worker is not, so each job gets a fresh event loop. That is correct and
it is not free — a loop per job costs a few milliseconds, which is noise beside
a graph that takes hundreds. A worker running with `--pool=gevent` would need
this revisited; the deployment in `infra/` uses prefork, which is what the
sandbox queue will want in 2.8 anyway.

Idempotency, and what "worker crash loses no work" actually promises
--------------------------------------------------------------------
`task_acks_late` means a job whose worker dies is redelivered, which means a job
can run twice. Everything a run does is written under a key derived from the
case id — the journal list, the state snapshot, the evidence-store rows — so a
second execution overwrites rather than accumulates: `EvidenceStore.save` clears
a case's child rows before rewriting them, and the journal is reset at the top
of the task for the same reason. What is *not* promised is exactly-once
execution of side effects outside those keys. There are none today. An agent
that acquires one — a takedown request, an alert to a bank — has to carry its
own idempotency key, and this paragraph is where that requirement is recorded.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict

from celery import Task

from schema.models import InvestigationEventKind, InvestigationState
from services.api.investigations.runner import Run, drive
from services.api.jobs.journal import RedisJournal, dead_letter

from .celery_app import app

#: Default duration of the sandbox probe. 90 seconds because that is the shape
#: task 1.8's acceptance criterion names — "a 90-second APK-shaped stub runs off
#: the request path" — and because it is comfortably longer than any HTTP client
#: will wait, which is the property being demonstrated.
SANDBOX_PROBE_SECONDS = 90


class InvestigationTask(Task):
    """Retry policy and dead-lettering, shared by every investigation job.

    A class rather than decorator arguments because `on_failure` is the half of
    the policy that decorators cannot express: what happens when the retries are
    spent. A job that is simply dropped at that point is work the system
    silently forgot, which is the failure mode a dead-letter queue exists for.
    """

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_jitter = True
    acks_late = True
    reject_on_worker_lost = True
    #: The result is the evidence-store row, not this. Storing it twice invites
    #: a reader to trust the copy that expires.
    ignore_result = True

    def on_failure(
        self, exc: BaseException, task_id: str, args: Any, kwargs: Any, einfo: Any
    ) -> None:
        dead_letter(
            {
                "task": self.name,
                "task_id": task_id,
                "case_id": (kwargs or {}).get("case_id"),
                "org_id": (kwargs or {}).get("org_id"),
                "error": f"{type(exc).__name__}: {exc}"[:400],
            }
        )


@app.task(bind=True, base=InvestigationTask, name="aegis.investigate")
def run_investigation(
    self: Task, *, case_id: str, org_id: str, state_json: str
) -> Dict[str, Any]:
    """Execute one investigation's graph, off the request path.

    The journal already holds the `accepted` event the API wrote before sending
    this message, so a client that connected in the gap has the node plan and
    this picks up at sequence 2. On a *redelivery* that is no longer true — the
    previous attempt's events are still there — so the journal is truncated back
    to its accepted event first, which is what makes a re-run produce one
    timeline rather than two interleaved ones.
    """
    state = InvestigationState.model_validate_json(state_json)
    journal = RedisJournal(org_id, case_id)
    _reset_journal(journal)

    run = Run(state, org_id, journal=journal)
    started = time.perf_counter()
    asyncio.run(drive(run))
    return {
        "case_id": case_id,
        "status": run.state.status.value,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def _reset_journal(journal: RedisJournal) -> None:
    """Drop everything this task would otherwise append twice.

    Only matters on a redelivery, and it is written to be right without
    assuming who wrote the journal. The normal shape is one `accepted` event
    from the API, which must survive — a client that reconnects after a
    redelivery still needs the node plan — so `LTRIM 0 0` keeps it and, on a
    first delivery, is a no-op because it is the only element. Anything else at
    the head means this journal was not written by the submission path, and the
    safe reading is that none of it belongs to this attempt.
    """
    try:
        head = journal.conn.lrange(journal.events_key, 0, 0)
        if head and _parse_kind(head[0]) == InvestigationEventKind.ACCEPTED.value:
            journal.conn.ltrim(journal.events_key, 0, 0)
        else:
            journal.conn.delete(journal.events_key)
    except Exception:
        pass


def _parse_kind(raw: str) -> str:
    try:
        return str(json.loads(raw).get("kind", ""))
    except Exception:
        return ""


@app.task(name="aegis.sandbox.probe", ignore_result=False)
def sandbox_probe(seconds: int = SANDBOX_PROBE_SECONDS) -> Dict[str, Any]:
    """A long, deliberately inert job on the sandbox queue.

    Two purposes, both real. It is task 1.8's acceptance probe — "a 90-second
    APK-shaped stub runs off the request path" is a claim you can only make by
    running one and watching the API stay responsive. And it is the placeholder
    task 2.8 replaces with actual APK static analysis, which is why it lives on
    `sandbox` and returns the shape a static-analysis result will: an artefact
    reference and a verdict slot, empty.

    It does nothing but sleep. Nothing is executed, nothing is downloaded, and
    when 2.8 fills this in that must stay true of the uploaded APK — static
    analysis only, network-less container, read-only mount. See
    docs/ARCHITECTURE.md §8.
    """
    time.sleep(max(0, int(seconds)))
    return {
        "task": "sandbox.probe",
        "seconds": int(seconds),
        "findings": [],
        "note": "placeholder for task 2.8 — APK static analysis, never execution",
    }


__all__ = ["SANDBOX_PROBE_SECONDS", "InvestigationTask", "run_investigation", "sandbox_probe"]
