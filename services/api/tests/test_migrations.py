"""
Alembic migrations — the fourth acceptance criterion of task 1.5, "migrations
run forward and back", checked by actually running them both ways.

Two things are being protected here, and they fail differently.

**Drift.** `Base.metadata.create_all` builds the schema for the zero-setup
database and Alembic builds it for a durable one. Two code paths to one schema
is two schemas the day someone edits a model and forgets a migration — and the
symptom is not a test failure, it is a production `column does not exist` weeks
later. `test_head_matches_the_models` upgrades an empty database to head and
asserts Alembic can find nothing to change, which is the same comparison
`--autogenerate` runs.

**One-way migrations.** A downgrade nobody executes is a rollback plan that has
never been tested, discovered at the worst possible moment. Every revision here
is run down as well as up on every test run.

These run on SQLite, which is the fallback store rather than the real one. Said
plainly because it matters: SQLite has no real `ALTER TABLE`, so Alembic
rebuilds tables in batch mode there, and a future revision that alters a column
is not proven by this file. The end-to-end verification for 1.5 ran the same
revisions against the compose PostgreSQL 16.6 — see docs/TASKS.md.
"""

from __future__ import annotations

import pathlib

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from services.api import models_db  # noqa: F401  (register the platform tables)
from services.api.db import Base
from services.api.stores import models as _evidence_models  # noqa: F401

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

PLATFORM_TABLES = {"organizations", "users", "case_records", "citizen_reports", "audit_events"}
EVIDENCE_TABLES = {
    "investigations",
    "evidence_items",
    "agent_results",
    "findings",
    "entities",
    "case_entities",
}
#: Added by 0003 — the role catalogue, revocable sessions, password resets.
RBAC_TABLES = {
    "roles",
    "permissions",
    "role_permissions",
    "user_sessions",
    "password_resets",
}


def _config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "services" / "api" / "migrations"))
    # Driving Alembic in-process must not reconfigure this process's logging.
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A private SQLite file, and the URL env.py will read."""
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_head_matches_the_models(db):
    """Upgrade an empty database to head; Alembic must find nothing to change.

    This is what keeps `create_all` and the migrations describing one schema.
    An empty diff means the two cannot have drifted.
    """
    url, engine = db
    command.upgrade(_config(url), "head")

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)

    assert diff == [], f"migrations have drifted from the models: {diff}"


def test_head_creates_every_table_the_models_declare(db):
    url, engine = db
    command.upgrade(_config(url), "head")
    assert _tables(engine) == set(Base.metadata.tables)
    assert _tables(engine) >= EVIDENCE_TABLES


def test_migrations_run_forward_and_back_and_forward(db):
    """The criterion, literally. Down to nothing, then up again."""
    url, engine = db
    cfg = _config(url)

    command.upgrade(cfg, "head")
    assert _tables(engine)

    command.downgrade(cfg, "base")
    assert _tables(engine) == set()

    command.upgrade(cfg, "head")
    assert _tables(engine) == set(Base.metadata.tables)


def test_head_creates_the_rbac_tables(db):
    """0003's five tables exist at head, and the columns it adds are on the
    tables it adds them to. `test_head_matches_the_models` already proves there
    is no drift; this states what the revision is *for*, so a future edit that
    quietly drops one fails with a name rather than a diff."""
    url, engine = db
    command.upgrade(_config(url), "head")
    assert _tables(engine) >= RBAC_TABLES
    users = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"role_id", "full_name", "phone", "email_verified", "last_login_at"} <= users
    events = {c["name"] for c in inspect(engine).get_columns("audit_events")}
    assert {"actor_user_id", "resource_type", "resource_id", "success", "ip"} <= events


def test_downgrading_the_auth_revision_leaves_the_users_alone(db):
    """Rolling back 0003 takes the RBAC tables and the columns it added, and
    leaves every user row where it was — the rollback plan for this change, run
    rather than described."""
    url, engine = db
    cfg = _config(url)
    command.upgrade(cfg, "head")

    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO organizations (id, slug, name, created_at) "
                "VALUES (1, 'aegis', 'AegisAI', '2026-08-26 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, org_id, disabled, "
                "created_at, email_verified, updated_at) VALUES "
                "(1, 'keep@aegis.local', 'x', 'owner', 1, 0, '2026-08-26 00:00:00', 0, "
                "'2026-08-26 00:00:00')"
            )
        )

    command.downgrade(cfg, "0002")
    remaining = _tables(engine)
    assert not (RBAC_TABLES & remaining)
    assert remaining >= PLATFORM_TABLES
    with engine.connect() as conn:
        assert conn.execute(text("SELECT email FROM users")).scalar() == "keep@aegis.local"


def test_downgrading_the_evidence_revision_leaves_the_platform_alone(db):
    """The split into two revisions has to be real.

    0001 baselines the tables that existed before Alembic; 0002 adds the
    evidence store. Rolling back 1.5 must take the six new tables and leave the
    users and saved cases where they were — which is the whole reason the
    baseline is a separate revision rather than one big initial migration.
    """
    url, engine = db
    cfg = _config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0001")

    remaining = _tables(engine)
    assert remaining == PLATFORM_TABLES
    assert not (EVIDENCE_TABLES & remaining)


def test_data_written_before_a_partial_downgrade_survives_it(db):
    """A rollback of 1.5 must not take the platform's rows with it.

    Rolling forward and back on an empty database proves the DDL is reversible.
    It does not prove the reversal is *safe*, and the thing a rollback exists to
    protect is rows.
    """
    url, engine = db
    cfg = _config(url)
    command.upgrade(cfg, "head")

    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO organizations (id, slug, name, created_at) "
                "VALUES (1, 'aegis', 'AegisAI', '2026-08-25 00:00:00')"
            )
        )

    command.downgrade(cfg, "0001")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT slug FROM organizations")).scalar() == "aegis"


def test_env_refuses_to_migrate_without_a_url(tmp_path, monkeypatch):
    """No silent fallback to the ephemeral database.

    `services.api.db` invents a temp-file SQLite when `DATABASE_URL` is unset,
    and that file is deleted when the process exits. Migrating it would be a
    deployment step that reports success and changes nothing — so the absence of
    a URL is an error with an explanation, not a default.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        command.upgrade(_config(""), "head")
    assert "DATABASE_URL" in str(exc.value)


def test_every_revision_is_reachable_from_head(db):
    """One linear history, no orphan or branched revisions.

    A branched history is legal in Alembic and unrunnable in a deployment; the
    error it produces names a revision hash and nothing else. Catching it here
    costs one assertion.
    """
    from alembic.script import ScriptDirectory

    url, _ = db
    script = ScriptDirectory.from_config(_config(url))
    heads = script.get_heads()
    assert len(heads) == 1, f"branched migration history: {heads}"
    revisions = [r.revision for r in script.walk_revisions()]
    assert revisions == ["0003", "0002", "0001"], revisions
