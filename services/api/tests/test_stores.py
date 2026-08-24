"""
Backing-store probes report honestly and never break the request path.

These run in two very different environments and must be meaningful in both:
a developer machine with `make up` running (all four reachable) and CI, which
has no stack at all (none reachable). So nothing here asserts reachability —
that would either fail on CI or pass vacuously. What is asserted is the shape,
the invariants, and the two properties that would actually hurt if they broke:
the probe must never raise, and it must never make /api/health slow.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from services.api.main import app
from services.api.stores import probe as store_probe

STORES = ("postgres", "neo4j", "qdrant", "redis")


def test_probe_reports_every_store():
    r = store_probe.probe_all(force=True)
    assert set(r) == set(STORES)


def test_probe_records_have_the_expected_shape():
    for name, rec in store_probe.probe_all(force=True).items():
        assert set(rec) >= {"reachable", "in_use", "serving", "endpoint", "detail"}, name
        assert isinstance(rec["reachable"], bool), name
        assert isinstance(rec["in_use"], bool), name
        # Something must be named as serving this concern, reachable or not —
        # that is the fallback the degradation invariant promises.
        assert rec["serving"], name


def _all_ports_dead(monkeypatch):
    """Point every probe at a port nothing listens on.

    `settings` is a frozen dataclass, so its fields cannot be reassigned;
    replacing the module's reference with an equivalent namespace is both
    simpler and closer to how the code actually reads config — by attribute,
    at call time.
    """
    dead = SimpleNamespace(
        pg_host="127.0.0.1", pg_port=1,
        neo4j_host="127.0.0.1", neo4j_bolt_port=1,
        qdrant_host="127.0.0.1", qdrant_port=1,
        redis_host="127.0.0.1", redis_port=1,
        # Since 1.5 the Postgres probe also reads which engine the evidence
        # store is actually bound to, so the double has to carry it. None is
        # the zero-setup default: the ephemeral SQLite, nothing configured.
        database_url=None,
    )
    monkeypatch.setattr(store_probe, "settings", dead)


def test_probe_never_raises_against_a_dead_port(monkeypatch):
    """A closed port is information, not an exception.

    Port 1 is reserved and never listening, so this exercises the failure path
    deterministically rather than hoping the real stack is down.
    """
    _all_ports_dead(monkeypatch)

    r = store_probe.probe_all(force=True)
    for name in STORES:
        assert r[name]["reachable"] is False, name
        assert r[name]["detail"], f"{name} gave no reason for being unreachable"


def test_unreachable_stores_are_bounded_in_time(monkeypatch):
    """Four dead stores must not add a visible delay to a health check."""
    _all_ports_dead(monkeypatch)

    start = time.perf_counter()
    store_probe.probe_all(force=True)
    elapsed = time.perf_counter() - start
    budget = 4 * store_probe.PROBE_TIMEOUT_S + 1.0
    assert elapsed < budget, f"probing four dead stores took {elapsed:.2f}s (budget {budget:.2f}s)"


def test_results_are_cached():
    """The request path pays for at most one probe per TTL."""
    first = store_probe.probe_all(force=True)
    second = store_probe.probe_all()
    assert second is first, "second call re-probed instead of using the cache"


def test_in_use_implies_reachable_or_degraded():
    """The invariant that keeps this honest as Phase 3 lands.

    If a store is ever marked in_use, then either it is reachable, or the
    health payload must say the system is degraded. Silently routing real work
    at an unreachable store while reporting a clean bill of health is the exact
    failure this endpoint exists to prevent.
    """
    r = store_probe.probe_all(force=True)
    tags = store_probe.degraded_tags()
    for name, rec in r.items():
        if rec["in_use"] and not rec["reachable"]:
            assert tags, (
                f"{name} is in_use but unreachable, and nothing was reported as degraded"
            )


def test_no_store_absence_is_reported_as_degraded_yet():
    """A clean clone with no Docker is the documented default, not a fault.

    Until Phase 3 routes work to these stores, their absence must not add a
    degraded tag — crying wolf on every fresh checkout trains people to ignore
    the field that matters.
    """
    assert store_probe.degraded_tags() == []


def test_health_exposes_infrastructure():
    body = TestClient(app).get("/api/health").json()
    assert "infrastructure" in body
    assert set(body["infrastructure"]) == set(STORES)
    assert body["ok"] is True


def test_health_is_fast_with_the_stack_in_any_state():
    """Health stays responsive whether the stack is up, down, or half up."""
    client = TestClient(app)
    client.get("/api/health")  # prime the cache
    start = time.perf_counter()
    for _ in range(10):
        assert client.get("/api/health").status_code == 200
    per_call_ms = (time.perf_counter() - start) * 100
    assert per_call_ms < 250, f"/api/health averaged {per_call_ms:.0f}ms per call"


# --- since 1.5, `in_use` for Postgres is a real answer ----------------------


def _bound_to(monkeypatch, url):
    """Point the probe's config at a given DATABASE_URL, ports still dead."""
    _all_ports_dead(monkeypatch)
    monkeypatch.setattr(store_probe.settings, "database_url", url)


def test_the_health_line_and_the_probe_name_the_same_engine(monkeypatch):
    """`/api/health` reports `database.backend` from the same function the probe
    uses, so the two cannot claim different stores are holding the case files."""
    _bound_to(monkeypatch, "postgresql+psycopg://aegis@127.0.0.1:5432/aegis")
    assert store_probe.serving_engine() == "postgres"
    _bound_to(monkeypatch, "sqlite:///aegis.db")
    assert store_probe.serving_engine() == "sqlite"
    _bound_to(monkeypatch, "mysql+pymysql://x@y/z")
    # An unrecognised dialect is named, not filed under "sqlite". A wrong
    # store in a status line is the one lie this project cannot afford.
    assert store_probe.serving_engine() == "mysql+pymysql"


def test_postgres_is_not_in_use_on_the_zero_setup_default(monkeypatch):
    """Reachable is not the same as in use, and the default is not degraded.

    A developer running `make up` has Postgres listening while the API is still
    on the ephemeral SQLite. Reporting that as "postgres: in use" would advertise
    a durability the deployment does not have.
    """
    _bound_to(monkeypatch, None)
    pg = store_probe.probe_all(force=True)["postgres"]
    assert pg["in_use"] is False
    assert pg["serving"] == "sqlite:ephemeral"
    assert store_probe.degraded_tags() == []


def test_postgres_is_in_use_when_the_evidence_store_is_bound_to_it(monkeypatch):
    _bound_to(monkeypatch, "postgresql+psycopg://aegis@127.0.0.1:5432/aegis")
    pg = store_probe.probe_all(force=True)["postgres"]
    assert pg["in_use"] is True
    assert pg["serving"] == "postgres"


def test_an_unreachable_postgres_is_degraded_only_when_it_was_asked_for(monkeypatch):
    """The degradation invariant, pointed the right way round.

    An operator who configured Postgres and cannot reach it is degraded and must
    be told. One who never configured it is running the documented default, and
    tagging that would cry wolf on every clean clone.
    """
    _bound_to(monkeypatch, "postgresql+psycopg://aegis@127.0.0.1:1/aegis")
    assert store_probe.degraded_tags() == ["store:postgres:unreachable"]

    _bound_to(monkeypatch, "sqlite:///aegis.db")
    assert store_probe.degraded_tags() == []
