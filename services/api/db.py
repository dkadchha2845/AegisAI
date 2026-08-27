"""
Database — optional, in-memory by default.

The rest of the service still runs with no database at all: leave `DATABASE_URL`
unset and this module gives you an ephemeral in-memory SQLite that lives for the
process, so the clean-clone demo boots with zero setup and `db:ephemeral` is
reported honestly. Point `DATABASE_URL` at a file (`sqlite:///aegis.db`) or a
Postgres URL and the very same code persists — that is the whole design: one
path, in-memory until you ask for durability.

SQLAlchemy is the one new hard dependency this adds. It is pure-Python and needs
no server for the default in-memory mode, so it does not break the "runs offline
on a clean clone" promise; it only *enables* persistence when you configure it.
"""

from __future__ import annotations

import atexit
import os
import tempfile
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for every mapped class in the service.

    A real class rather than `declarative_base()`. The factory returns a value
    whose type mypy cannot follow, so every `class X(Base)` in `models_db.py`
    and `stores/models.py` reports "invalid base class" — twenty-three errors in
    a gate that is kept at zero precisely so a new one is visible. SQLAlchemy 2.0
    added this form for exactly that reason; the mapping behaviour is identical,
    and both the annotated (`Mapped[int]`) and legacy (`Column(...)`) styles in
    this repository work unchanged underneath it.
    """

#: True when running the ephemeral (no DATABASE_URL) database — surfaced on
#: /api/health. Still ephemeral: the temp file below is unique per process and
#: deleted on exit, so a clean clone boots with zero setup and nothing persists.
EPHEMERAL = settings.database_url is None

_kwargs: dict = {}

if settings.database_url:
    # Operator-configured store — honour it exactly. A shared in-memory URL still
    # needs StaticPool; a file or Postgres URL uses normal pooling.
    _url = settings.database_url
    if _url.startswith("sqlite"):
        _kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if ":memory:" in _url or _url == "sqlite://":
            _kwargs["poolclass"] = StaticPool
else:
    # Ephemeral default: a temp FILE, not a shared in-memory connection.
    #
    # A shared `:memory:` database needs StaticPool — one connection reused for
    # every thread — because a second connection to `:memory:` opens a *different*
    # empty database. But FastAPI serves sync routes from a threadpool, and a
    # single sqlite connection driven from many threads at once segfaults the
    # native sqlite library (reproducibly, under a few concurrent requests). A
    # temp file sidesteps this entirely: each thread checks out its own
    # connection, sqlite serialises file access itself, and the file is deleted
    # on exit — so this is still zero-config and still ephemeral, just crash-safe.
    _tmp = tempfile.NamedTemporaryFile(prefix="aegis-", suffix=".db", delete=False)
    _tmp.close()
    _url = f"sqlite:///{_tmp.name}"
    _kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

    @atexit.register
    def _cleanup_ephemeral_db() -> None:  # pragma: no cover - process teardown
        try:
            os.unlink(_tmp.name)
        except OSError:
            pass

engine = create_engine(_url, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create tables. Idempotent — safe to call on every startup.

    This is the zero-setup path, and it is not the migration path. `create_all`
    is right for the ephemeral database a clean clone boots on: there is no
    prior version to migrate *from*, and requiring `alembic upgrade` before the
    demo runs would trade the whole "clone and run" promise for nothing.

    A durable deployment uses Alembic instead — `services/api/migrations`, or
    `make migrate`. The two cannot drift apart unnoticed:
    `test_migrations.py::test_head_matches_models` upgrades an empty database to
    head and asserts the result is exactly `Base.metadata`, which is what
    `create_all` would have produced.
    """
    from . import models_db
    from .stores import models as _store_models  # noqa: F401  (task 1.5 tables)

    # Before `create_all`, deliberately — see the docstring below.
    _refuse_if_stale(models_db)
    Base.metadata.create_all(bind=engine)


class StaleSchema(RuntimeError):
    """A durable database whose schema is behind the code. See `_refuse_if_stale`."""


def _refuse_if_stale(models_db) -> None:  # type: ignore[no-untyped-def]
    """Refuse to start on a durable database that predates the current models.

    `create_all` adds missing **tables**. It does not add a **column** to a
    table that already exists — so a durable database created before a revision
    that alters one comes back up looking fine and then fails on the first query
    with `no such column`, somewhere far from the cause.

    This is not hypothetical here. The rename to AegisAI broke demo login on
    every pre-existing database for exactly this shape of reason, and no test
    saw it because tests seed a fresh ephemeral database where the problem
    cannot occur (see the Working agreement in docs/TASKS.md). One column check
    at boot turns a confusing runtime error into a message that names the fix.

    **This raises rather than warning, and it runs before `create_all`.** Both
    halves matter, and both were learned by getting them wrong:

      * Warning and carrying on lets `create_all` create the revision's new
        *tables* while its new *columns* stay missing. `alembic upgrade` then
        fails on `table roles already exists` — the correct and loud failure
        `0001_platform_baseline.py` documents — and the operator is worse off
        than before they read the warning.
      * Booting anyway produces an API that answers 500 to every request that
        touches a user. Refusing to start, with the fix in the message, is the
        same choice `migrations/env.py` already makes when `DATABASE_URL` is
        unset: a deployment error should fail where it happened.

    The zero-setup path is untouched — an ephemeral database has no prior
    version to be behind — and a database this cannot inspect is not one it
    should refuse to start on.
    """
    if EPHEMERAL:
        return
    try:
        from sqlalchemy import inspect

        inspector = inspect(engine)
        if "users" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("users")}
        missing = {c.name for c in models_db.User.__table__.columns} - columns
        if not missing:
            return
        on_alembic = "alembic_version" in inspector.get_table_names()
        bring_forward = (
            "    make migrate"
            if on_alembic
            # A database built by `create_all` has no revision history, so it
            # must be stamped at the revision it already matches rather than
            # upgraded from nothing — 0001's docstring is the long version.
            else "    .venv/bin/alembic stamp 0002 && make migrate"
        )
        message = (
            "This database is older than the current schema — `users` is missing "
            f"{', '.join(sorted(missing))}.\n"
            "`create_all` adds tables, never columns, so every request that reads "
            "a user would fail.\n\n"
            "Bring the database forward, then start again:\n\n"
            f"{bring_forward}\n\n"
            "Or, for a throwaway development database, delete it and let it reseed."
        )
    except StaleSchema:
        raise
    except Exception:
        # An inspection failure is not a reason to refuse to boot.
        return
    raise StaleSchema(message)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a request-scoped session, always closed.

    Annotated `Iterator[Session]`, not `Session`: this is a generator, and
    FastAPI reads that from the function object rather than from the hint. The
    old annotation described what a caller receives instead of what the function
    returns, which is a difference mypy is right about.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def degraded() -> list[str]:
    return ["db:ephemeral"] if EPHEMERAL else []
