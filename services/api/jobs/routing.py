"""
Which queue a job belongs on, and how to find it again — task 1.8.

**Why it exists.** Three queues by cost class only help if something decides
which one a job goes on, and if a job already running can be found and stopped.
Both are small decisions with a sharp edge, so they live here rather than inside
the runner: the cost-class rule is a *hint* drawn from untrusted metadata, and
that is a sentence worth having somewhere a reader will find it.

**What it consumes.** An `InvestigationState`'s evidence items — specifically
the filename and the declared MIME type, which are the only things known about
an artefact at dispatch time.

**What it outputs.** A queue name, and a Redis-backed memory of which Celery
task id is running which case.

**How it connects.** `investigations/runner.py` calls `queue_for()` when it
sends and `revoke_task()` when erasure cancels.

**How it is evaluated.** `test_jobs_dispatch.py`: each cost class routes where
it should, an unlabelled submission takes the cheap queue, and the queue name is
always one the Celery app actually declares — a routing table naming a queue no
worker consumes is a job that never runs.

**Limitations, stated — read this before task 2.8.** `EvidenceItem.kind` is
`UNKNOWN` at dispatch: the magic-byte sniff runs on the graph's classifier node,
which is deliberate (see `intake.py`) and is on the far side of this decision.
So the cost class is chosen from `declared_type` and the filename extension —
data the contract explicitly marks "recorded, never trusted for routing".

That is sound for *scheduling*, which is all it is: an APK renamed `photo.jpg`
runs on `fast` instead of `sandbox`, which costs a worker slot for a while and
tells no lies. It is **not** sound as a security boundary, and 2.8 must not
treat it as one. When the APK agent brings the network-less, read-only container
that makes `sandbox` a real boundary, the isolation has to be enforced where the
sniffed type is known — inside the agent, or by re-dispatching after the
classifier node — and not by the guess made here.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Optional

from schema.models import InvestigationState

from . import broker

#: Filename extensions and declared MIME prefixes per cost class. Extensions
#: rather than `InputType`, because `InputType` is not known yet — see the
#: limitation above.
_SANDBOX_EXTENSIONS = {".apk", ".xapk", ".apks", ".aab", ".dex", ".jar"}
_SANDBOX_MIME = ("application/vnd.android.package-archive", "application/java-archive")
_SLOW_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus",
}
_SLOW_MIME = ("video/", "audio/")


def _task_key(org_id: str, case_id: str) -> str:
    return f"aegis:inv:task:{org_id}:{case_id}"


def _suffix(filename: Optional[str]) -> str:
    if not filename:
        return ""
    return PurePosixPath(filename).suffix.lower()


def queue_for(state: InvestigationState) -> str:
    """The cost class this investigation should run on.

    The most expensive class any single artefact suggests wins: a submission of
    one screenshot and one APK is an APK submission for scheduling purposes,
    because the graph runs once over all of it and takes as long as its slowest
    part.
    """
    from services.worker.celery_app import FAST, SANDBOX, SLOW

    classes = {FAST}
    for item in state.inputs:
        declared = (item.declared_type or "").strip().lower()
        suffix = _suffix(item.filename)
        if suffix in _SANDBOX_EXTENSIONS or declared in _SANDBOX_MIME:
            classes.add(SANDBOX)
        elif suffix in _SLOW_EXTENSIONS or declared.startswith(_SLOW_MIME):
            classes.add(SLOW)

    if SANDBOX in classes:
        return SANDBOX
    if SLOW in classes:
        return SLOW
    return FAST


# --------------------------------------------------------------------------
# Finding a running job again
# --------------------------------------------------------------------------


def remember_task(org_id: str, case_id: str, task_id: str, *, ttl_s: int = 6 * 3600) -> None:
    """Record which Celery task is running which case. Never raises.

    In Redis rather than on the `Run`, because the API process that erases a
    case is not necessarily the one that dispatched it — and an erasure that
    silently fails to stop the worker is an erasure the worker undoes when it
    finishes and writes the rows back.
    """
    try:
        broker.client().set(_task_key(org_id, case_id), task_id, ex=ttl_s)
    except Exception:
        pass


def task_id(org_id: str, case_id: str) -> Optional[str]:
    try:
        value = broker.client().get(_task_key(org_id, case_id))
        return str(value) if value else None
    except Exception:
        return None


def forget_task(org_id: str, case_id: str) -> None:
    try:
        broker.client().delete(_task_key(org_id, case_id))
    except Exception:
        pass


def revoke_task(org_id: str, case_id: str) -> bool:
    """Stop the worker running this case. Returns whether there was one.

    `terminate=True` because a revoke without it only prevents a job from
    *starting*, and erasure's whole problem is the job that is already halfway
    through and about to write the rows back. SIGTERM rather than SIGKILL so the
    task's own `except CancelledError` path — which journals the cancellation —
    gets a chance to run.
    """
    running = task_id(org_id, case_id)
    if not running:
        return False
    try:
        from services.worker.celery_app import app as celery_app

        celery_app.control.revoke(running, terminate=True, signal="SIGTERM")
        forget_task(org_id, case_id)
        return True
    except Exception:
        return False


__all__ = ["forget_task", "queue_for", "remember_task", "revoke_task", "task_id"]
