"""
The async job system — task 1.8.

Four modules, split by the question each answers:

* `broker.py` — *is there a queue?* One cached, bounded, never-raising probe,
  and the single Redis URL the API and the worker share.
* `journal.py` — *what is this investigation doing?* 1.6's progress journal,
  behind an interface, in this process's memory or in Redis.
* `routing.py` — *which queue, and how do I stop it?* Cost-class selection and
  the case-to-task-id memory erasure needs.
* The worker itself lives in `services/worker/`, because it is a separate
  process with a separate entry point; it imports from here rather than the
  reverse, so nothing in the request path depends on Celery being importable.

The whole package is optional at runtime. With no reachable Redis the API
behaves exactly as it did after 1.6 — graph on the event loop, journal on the
heap — and says so, in `degraded` and on `/api/health`. That is invariant 4, and
it is the reason `available()` returns a reason string rather than a bare bool.
"""

from . import broker, journal, routing

__all__ = ["broker", "journal", "queue_purpose", "routing"]


def queue_purpose() -> dict:
    """What each cost class is for, for `/api/health`.

    Lazy and forgiving: the API must report its execution mode even on an
    install where Celery is not importable, and "we could not read the queue
    table" is a smaller thing to say than a 500 on the status endpoint.
    """
    try:
        from services.worker.celery_app import QUEUE_PURPOSE

        return dict(QUEUE_PURPOSE)
    except Exception:
        return {}
