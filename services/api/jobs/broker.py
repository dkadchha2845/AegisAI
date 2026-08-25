"""
Reaching Redis, and admitting when we cannot — task 1.8.

**Why it exists.** Everything else in 1.8 needs one answer first: is there a
queue to put work on? That question has to be cheap, bounded and cached,
because it is asked on the request path — `POST /api/investigations` decides
between a worker and this process on the strength of it — and it must never
raise, because a broker that is down is a degradation the API reports rather
than an error it returns. The store probe in `stores/probe.py` already
established that shape for `/api/health`; this is the same discipline applied to
a decision instead of a status line.

**What it consumes.** `settings.redis_url`, or the host/port pair the compose
stack is described by.

**What it outputs.** `redis_url()`, a client for the API side, and
`available()` — a cached boolean with a reason attached.

**How it connects.** `investigations/runner.py` calls `available()` to choose a
dispatcher. `jobs/journal.py` uses the clients. `services/worker/celery_app.py`
takes its broker URL from `redis_url()`, so the API and the worker cannot end up
pointed at different Redises.

**How it is evaluated.** `test_jobs_queue.py`: the URL is derived from host/port
when unset and honoured when set, the probe caches, an unreachable broker
returns False with a reason rather than raising, and the credentials in a URL
never reach `describe()`.

**Limitations, stated.** `available()` proves that *a Redis* answered PING. It
does not prove a worker is consuming the queue — a broker with no worker
accepts the job and nothing runs it. That is visible on `/api/health` as a
`workers` count read from Celery's own inspect protocol, which is a live call
and therefore not on the request path: submission degrades on the broker being
unreachable, not on the fleet being empty.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from ..config import settings

#: How long a reachability answer is reused. Same reasoning as `stores/probe.py`:
#: long enough that a burst of submissions costs one probe, short enough that
#: starting the stack shows up without restarting the API.
PROBE_TTL_S = 10.0

#: Socket timeout for the probe and for the client the API uses. Deliberately
#: short: this runs while a citizen waits for a 202.
TIMEOUT_S = 0.5

#: Put on an investigation when the broker answered PING and then refused the
#: message. That is a real, per-case failure — this submission was supposed to
#: go to a worker and did not — so it belongs on the case.
UNAVAILABLE = "queue:unavailable"

#: Reported on the 202 and on the `accepted` event when the graph will run in
#: the API process. Deliberately **not** put on `InvestigationState.degraded`.
#:
#: Where an investigation executes is a property of the deployment, not of the
#: case: the analysis is identical either way, and what differs is whether a
#: restart loses the run. `stores/probe.degraded_tags()` already settled the
#: same question for Postgres — "an absent stack is not a degradation, it is the
#: documented zero-setup default, and reporting it as degraded would cry wolf on
#: every clean clone" — and 1.7's own notes record what happens when a tag is
#: raised on every case: the field becomes one people ignore. So the client is
#: told at submission, `/api/health` reports `execution.mode` always, and the
#: case file stays a record of the *analysis* that was reduced.
IN_PROCESS = "queue:in_process"

#: The one queue state that is unambiguously broken: a reachable broker that no
#: worker is consuming. The API has stopped running the graph itself and is
#: handing work to a queue that goes nowhere. Health-level, like
#: `store:postgres:unreachable`, and raised on the same principle — only for a
#: capability the deployment is actually trying to use.
NO_WORKERS = "queue:no_workers"


@dataclass
class _Cached:
    at: float = 0.0
    ok: bool = False
    reason: str = "not probed"


_cache = _Cached()


def redis_url() -> str:
    """The one Redis URL the API and the worker both use.

    Derived from the host/port the compose stack is described by unless
    `AEGIS_REDIS_URL` is set, so the zero-config path needs no new variable and
    a deployment with a password or TLS has somewhere to put it.
    """
    if settings.redis_url:
        return settings.redis_url
    return f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"


def describe(url: Optional[str] = None) -> str:
    """The broker URL with any credentials removed.

    `/api/health` reports this and so do error messages. A Redis URL may carry a
    password, and "secrets: environment only" is worth nothing if the endpoint
    prints them back out.
    """
    parts = urlsplit(url or redis_url())
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def client(**kwargs: Any) -> Any:
    """A synchronous Redis client. Used by the worker and by the probe."""
    import redis

    return redis.Redis.from_url(
        redis_url(),
        socket_timeout=kwargs.pop("socket_timeout", TIMEOUT_S),
        socket_connect_timeout=kwargs.pop("socket_connect_timeout", TIMEOUT_S),
        decode_responses=True,
        **kwargs,
    )


def async_client(**kwargs: Any) -> Any:
    """An asyncio Redis client. Used by the SSE path, which must not block."""
    import redis.asyncio as aioredis

    return aioredis.Redis.from_url(
        redis_url(),
        socket_timeout=kwargs.pop("socket_timeout", TIMEOUT_S),
        socket_connect_timeout=kwargs.pop("socket_connect_timeout", TIMEOUT_S),
        decode_responses=True,
        **kwargs,
    )


def probe() -> Tuple[bool, str]:
    """PING, uncached. Returns (ok, reason). Never raises."""
    try:
        conn = client()
        try:
            conn.ping()
            return True, "PONG"
        finally:
            conn.close()
    except Exception as exc:  # redis raises a family of connection errors
        return False, f"{type(exc).__name__}: {exc}"[:200]


def available(*, force: bool = False) -> Tuple[bool, str]:
    """Is there a broker to enqueue onto? Cached for `PROBE_TTL_S`.

    False when the queue is switched off, so callers have one question to ask
    rather than two — a disabled queue and an unreachable one both mean "run it
    here", and the reason string is what distinguishes them afterwards.
    """
    if not settings.queue_enabled:
        return False, "disabled by AEGIS_QUEUE"

    now = time.monotonic()
    if not force and _cache.at and now - _cache.at < PROBE_TTL_S:
        return _cache.ok, _cache.reason

    ok, reason = probe()
    _cache.at = now
    _cache.ok = ok
    _cache.reason = reason
    return ok, reason


def reset_cache() -> None:
    """Forget the cached answer. For tests, and for `/api/health?force=1`."""
    _cache.at = 0.0
    _cache.ok = False
    _cache.reason = "not probed"


__all__ = [
    "IN_PROCESS",
    "NO_WORKERS",
    "PROBE_TTL_S",
    "TIMEOUT_S",
    "UNAVAILABLE",
    "async_client",
    "available",
    "client",
    "describe",
    "probe",
    "redis_url",
    "reset_cache",
]
