"""
Database — optional, in-memory by default.

The rest of the service still runs with no database at all: leave `DATABASE_URL`
unset and this module gives you an ephemeral in-memory SQLite that lives for the
process, so the clean-clone demo boots with zero setup and `db:ephemeral` is
reported honestly. Point `DATABASE_URL` at a file (`sqlite:///kavach.db`) or a
Postgres URL and the very same code persists — that is the whole design: one
path, in-memory until you ask for durability.

SQLAlchemy is the one new hard dependency this adds. It is pure-Python and needs
no server for the default in-memory mode, so it does not break the "runs offline
on a clean clone" promise; it only *enables* persistence when you configure it.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings

Base = declarative_base()

#: True when running the ephemeral in-memory database — surfaced on /api/health.
EPHEMERAL = settings.database_url is None

_url = settings.database_url or "sqlite://"  # sqlite:// == in-memory

_kwargs: dict = {}
if _url.startswith("sqlite"):
    # FastAPI serves sync routes from a threadpool; the in-memory DB must be a
    # single shared connection or each thread would get its own empty database.
    _kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in _url or _url == "sqlite://":
        _kwargs["poolclass"] = StaticPool

engine = create_engine(_url, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create tables. Idempotent — safe to call on every startup."""
    from . import models_db  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """FastAPI dependency: a request-scoped session, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def degraded() -> list[str]:
    return ["db:ephemeral"] if EPHEMERAL else []
