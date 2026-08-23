"""
Connectivity probes for the backing stores.

`/api/health` must answer "which infrastructure is actually reachable?" with a
checked fact rather than a hope — the same standard the classifier block is held
to. This module provides that, under three constraints that shape the whole
design:

1. **It must never block the request path.** Four network round trips on every
   health call is a self-inflicted outage. Probes use a short timeout and are
   cached; a health request either reuses a recent result or pays one bounded
   probe.

2. **It must never raise.** A probe failure is information, not an error. Every
   path returns a record; nothing propagates.

3. **It must not lie about what is being used.** Reachable is not the same as
   in-use. Postgres can be up and healthy while the API is still writing to
   SQLite, because the migration is Phase 3. Reporting "postgres: ok" then would
   imply a capability that does not exist, so `in_use` is tracked separately and
   is honest about it.

Deliberately no psycopg / neo4j / qdrant-client dependency here. Those arrive in
Phase 3 with the actual adapters; a TCP or HTTP liveness check needs none of
them, and adding three clients in Phase 0 to print one boolean each would be
the "every algorithm should have a clear purpose" rule broken for a status line.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..config import settings

#: Probe results are cached this long. Long enough that a dashboard polling
#: /api/health every few seconds costs nothing; short enough that starting the
#: stack shows up without a restart.
CACHE_TTL_S = 10.0

#: Per-probe socket timeout. Generous enough for a container that is up but
#: busy, tight enough that four unreachable stores cost well under a second.
PROBE_TIMEOUT_S = 0.35


@dataclass
class StoreStatus:
    """One store's answer. `reachable` and `in_use` are deliberately distinct."""

    name: str
    reachable: bool
    #: Whether the API currently routes real work here. False for everything
    #: until Phase 3 migrates each store; saying otherwise would overstate the
    #: system's capability.
    in_use: bool
    #: The implementation actually serving this concern right now.
    serving: str
    endpoint: str
    latency_ms: Optional[int] = None
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "reachable": self.reachable,
            "in_use": self.in_use,
            "serving": self.serving,
            "endpoint": self.endpoint,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }


@dataclass
class _Cache:
    at: float = 0.0
    value: Dict[str, Dict[str, Any]] = field(default_factory=dict)


_cache = _Cache()


def _tcp_probe(host: str, port: int) -> tuple[bool, Optional[int], str]:
    """Can we open a TCP connection? Returns (ok, latency_ms, detail)."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_S):
            ms = int((time.perf_counter() - start) * 1000)
            return True, ms, ""
    except OSError as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def _redis_probe(host: str, port: int) -> tuple[bool, Optional[int], str]:
    """TCP plus an actual PING.

    Redis answers RESP on a raw socket, so a real liveness check costs one extra
    write. Worth it: an open port only proves something is listening, which on a
    developer's machine is as likely to be an unrelated service as Redis.
    """
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_S) as sock:
            sock.settimeout(PROBE_TIMEOUT_S)
            sock.sendall(b"PING\r\n")
            reply = sock.recv(64)
            ms = int((time.perf_counter() - start) * 1000)
            if reply.startswith(b"+PONG"):
                return True, ms, ""
            return False, ms, f"unexpected reply: {reply[:32]!r}"
    except OSError as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def _qdrant_probe(host: str, port: int) -> tuple[bool, Optional[int], str]:
    """Qdrant's readiness endpoint, via httpx (already a dependency)."""
    start = time.perf_counter()
    try:
        import httpx

        r = httpx.get(f"http://{host}:{port}/readyz", timeout=PROBE_TIMEOUT_S)
        ms = int((time.perf_counter() - start) * 1000)
        if r.status_code == 200:
            return True, ms, ""
        return False, ms, f"HTTP {r.status_code}"
    except Exception as exc:  # httpx raises a family of connect/timeout errors
        return False, None, f"{type(exc).__name__}: {exc}"


def probe_all(force: bool = False) -> Dict[str, Dict[str, Any]]:
    """Probe every store, cached. Never raises.

    `force=True` bypasses the cache — used by `make status` and by tests, not by
    the request path.
    """
    now = time.monotonic()
    if not force and _cache.value and (now - _cache.at) < CACHE_TTL_S:
        return _cache.value

    results: Dict[str, Dict[str, Any]] = {}

    # --- PostgreSQL: durable case + evidence store (Phase 1.5 / 3) ----------
    ok, ms, detail = _tcp_probe(settings.pg_host, settings.pg_port)
    results["postgres"] = StoreStatus(
        name="postgres",
        reachable=ok,
        in_use=False,
        serving="sqlite",
        endpoint=f"{settings.pg_host}:{settings.pg_port}",
        latency_ms=ms,
        detail=detail or "reachable; API still on SQLite until Phase 3",
    ).as_dict()

    # --- Neo4j: fraud entity graph (Phase 3.1) ------------------------------
    ok, ms, detail = _tcp_probe(settings.neo4j_host, settings.neo4j_bolt_port)
    results["neo4j"] = StoreStatus(
        name="neo4j",
        reachable=ok,
        in_use=False,
        serving="networkx",
        endpoint=f"{settings.neo4j_host}:{settings.neo4j_bolt_port}",
        latency_ms=ms,
        detail=detail or "reachable; graph still in-process NetworkX until Phase 3",
    ).as_dict()

    # --- Qdrant: semantic memory + RAG corpus (Phase 3.4) -------------------
    ok, ms, detail = _qdrant_probe(settings.qdrant_host, settings.qdrant_port)
    results["qdrant"] = StoreStatus(
        name="qdrant",
        reachable=ok,
        in_use=False,
        serving="in-house vector store",
        endpoint=f"{settings.qdrant_host}:{settings.qdrant_port}",
        latency_ms=ms,
        detail=detail or "reachable; retrieval still in-house until Phase 3",
    ).as_dict()

    # --- Redis: cache + Celery broker (Phase 1.8) ---------------------------
    ok, ms, detail = _redis_probe(settings.redis_host, settings.redis_port)
    results["redis"] = StoreStatus(
        name="redis",
        reachable=ok,
        in_use=False,
        serving="in-process cache",
        endpoint=f"{settings.redis_host}:{settings.redis_port}",
        latency_ms=ms,
        detail=detail or "reachable; queues arrive in Phase 1.8",
    ).as_dict()

    _cache.at = now
    _cache.value = results
    return results


def degraded_tags() -> list[str]:
    """Tags for `/api/health`'s `degraded` list.

    Only emitted for a store the API *would* be using. Today that is none of
    them, so an absent stack is not a degradation — it is the documented
    zero-setup default, and reporting it as degraded would cry wolf on every
    clean clone. This function grows a case per store as Phase 3 migrates each.
    """
    return []
