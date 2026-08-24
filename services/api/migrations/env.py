"""
Alembic environment — task 1.5.

**Why it exists.** `Base.metadata.create_all` builds today's schema on an empty
database and can do nothing else. It cannot add a column to a table that already
has rows, and it cannot tell you what version a database is on. A durable
evidence store needs both, because the row it will one day fail to migrate is a
case file.

**What it consumes.** `DATABASE_URL` from the environment, or `-x url=...` on
the command line, plus `Base.metadata` — which is the models, not a second
description of the schema.

**How it is evaluated.** `test_migrations.py`: upgrade to head on an empty
database, assert `compare_metadata` reports no difference from the models,
downgrade to base, and upgrade again. Forward *and* back, on every run.

**Limitations, stated.** SQLite cannot ALTER most things, so migrations run in
batch mode there — Alembic copies the table, which is correct and is also why a
migration that works on SQLite is not proof it works on PostgreSQL. Anything
touching an existing column should be exercised against the compose Postgres
before it is trusted. There is no `alembic stamp` automation for a database that
predates this: an existing SQLite file built by `create_all` must be stamped
once (`alembic stamp head`) or Alembic will try to create tables it already has.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

# `prepend_sys_path = .` in alembic.ini covers the normal invocation from the
# repository root; this covers being driven programmatically from a test, where
# the working directory is whatever pytest chose.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.api import models_db  # noqa: E402,F401  (platform tables)
from services.api.db import Base  # noqa: E402
from services.api.stores import models as _evidence_models  # noqa: E402,F401  (1.5 tables)

config = context.config
# `disable_existing_loggers=False`, and skippable. Alembic's stock template calls
# `fileConfig(name)`, whose default is to silence every logger already
# configured in the process — harmless from the command line and quietly
# destructive when a test drives migrations in-process and the rest of the suite
# then runs with logging switched off.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

#: The models are the schema. Autogenerate diffs against this, and the head-vs-
#: models test asserts the diff is empty — so the migrations cannot drift from
#: `models_db.py` and `stores/models.py` without a test going red.
target_metadata = Base.metadata


def _url() -> str:
    """Where to migrate. Explicit, and never guessed.

    Order: `-x url=...`, then `DATABASE_URL`. There is no fallback to the
    ephemeral temp-file database — migrating a database that is deleted when the
    process exits is a no-op dressed as a deployment step, and failing here says
    so out loud.
    """
    from_x = context.get_x_argument(as_dictionary=True).get("url")
    url = from_x or os.getenv("DATABASE_URL") or ""
    if not url.strip():
        raise SystemExit(
            "No database URL. Set DATABASE_URL, or pass `-x url=sqlite:///aegis.db`.\n"
            "The zero-setup ephemeral database has nothing to migrate: it is "
            "created by create_all at startup and deleted on exit."
        )
    return url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it — `alembic upgrade head --sql`.

    Kept because a production database is often migrated by a DBA reviewing a
    script, not by an application process holding DDL rights.
    """
    url = _url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=_is_sqlite(url),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    section: dict[str, Any] = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite has no real ALTER TABLE. Batch mode makes Alembic rebuild
            # the table instead, which is the only way a column change runs at
            # all on the fallback store.
            render_as_batch=_is_sqlite(url),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
