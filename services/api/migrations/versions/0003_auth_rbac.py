"""Auth & RBAC: roles, permissions, sessions, password resets, richer users and audit.

What this revision adds, and why each piece is here rather than in application code:

* **`roles` / `permissions` / `role_permissions`** — the role → capability map,
  made relational so a schema diagram and a SQL console can answer "who can
  manage users". The authority remains `services/api/permissions.py`;
  `auth.seed_rbac()` reconciles these rows against it on every boot.
* **`user_sessions`** — one row per issued token, which is what makes signing
  out revoke something. Only the token's `jti` is stored, never the token.
* **`password_resets`** — single-use, short-lived, and stored as a digest.
* **`users`** gains a profile (name, phone, avatar), `email_verified`,
  `updated_at`, `last_login_at` and `role_id`.
* **`audit_events`** gains `actor_user_id`, `resource_type`, `resource_id`,
  `success`, `ip` and `user_agent`.

**Backfills, and why they are in the migration.** The four `users` columns and
the two `audit_events` columns that are `NOT NULL` cannot be added to a table
that already has rows without a value for the existing ones. `updated_at` is
backfilled from `created_at` (the row has not been updated since it was made),
`email_verified` to false (nothing has verified anything — see the column's note
in `models_db.py`), and `audit_events.success` to true (every event recorded
before this revision was recorded at a point the action had already succeeded,
except the `login.failed` rows, which are handled explicitly below).

`role_id` is left NULL here on purpose. Populating it needs the `roles` rows,
which are seeded by the application and not by DDL; `seed_rbac()` reconciles
every user's `role_id` on the next boot, and a NULL in the meantime costs
nothing because `users.role` is what every query and every gate actually reads.

Revision ID: 0003
Revises: 0002
Created: 2026-08-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- the RBAC catalogue -------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_permissions_code"), "permissions", ["code"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_pair"),
    )
    op.create_index(
        op.f("ix_role_permissions_permission_id"), "role_permissions", ["permission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_role_permissions_role_id"), "role_permissions", ["role_id"], unique=False
    )

    # --- sessions -----------------------------------------------------------
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("jti", sa.String(length=48), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_sessions_created_at"), "user_sessions", ["created_at"])
    op.create_index(op.f("ix_user_sessions_jti"), "user_sessions", ["jti"], unique=True)
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"])

    # --- password resets ----------------------------------------------------
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_password_resets_token_hash"), "password_resets", ["token_hash"], unique=True
    )
    op.create_index(op.f("ix_password_resets_user_id"), "password_resets", ["user_id"])

    # --- users: profile, verification, timestamps, role key -----------------
    #
    # batch_alter_table because SQLite has no real ALTER; on PostgreSQL this
    # compiles to plain ALTER TABLE statements. The NOT NULL columns are added
    # with a server_default so existing rows get a value, and the default is
    # then dropped so the application supplies it from here on — leaving it in
    # place would make the database, not `models_db.py`, the authority on what
    # a new row looks like, and `test_head_matches_the_models` would see the
    # difference as drift.
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("full_name", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("phone", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("avatar_url", sa.String(length=512), nullable=True))
        batch.add_column(
            sa.Column(
                "email_verified", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key("fk_users_role_id", "roles", ["role_id"], ["id"])
    op.create_index(op.f("ix_users_role_id"), "users", ["role_id"])

    # An existing row has not been updated since it was created.
    op.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NOT NULL")

    with op.batch_alter_table("users") as batch:
        batch.alter_column("email_verified", server_default=None)
        batch.alter_column("updated_at", server_default=None)

    # --- audit: who, what kind of thing, whether it worked, from where ------
    with op.batch_alter_table("audit_events") as batch:
        batch.add_column(sa.Column("actor_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("resource_type", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("resource_id", sa.String(length=200), nullable=True))
        batch.add_column(
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(sa.Column("ip", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("user_agent", sa.String(length=256), nullable=True))
    op.create_index(op.f("ix_audit_events_actor_user_id"), "audit_events", ["actor_user_id"])
    op.create_index(op.f("ix_audit_events_resource_type"), "audit_events", ["resource_type"])

    # The one historical action that was a failure by definition. Every other
    # pre-existing row records something that had already happened.
    #
    # Written through the SQLAlchemy expression layer rather than as raw SQL,
    # so the boolean literal is rendered per dialect. `SET success = 0` is
    # accepted by SQLite, which has no boolean type, and rejected by PostgreSQL
    # with `column "success" is of type boolean but expression is of type
    # integer` — a migration that passes every test in this repository and
    # fails on the only database anyone deploys to. This file's own tests run
    # on SQLite and say so; that is what let it through.
    audit = sa.table(
        "audit_events",
        sa.column("success", sa.Boolean),
        sa.column("action", sa.String),
    )
    op.execute(
        audit.update().where(audit.c.action == op.inline_literal("login.failed"))
        .values(success=op.inline_literal(False))
    )

    with op.batch_alter_table("audit_events") as batch:
        batch.alter_column("success", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_resource_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_user_id"), table_name="audit_events")
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_column("user_agent")
        batch.drop_column("ip")
        batch.drop_column("success")
        batch.drop_column("resource_id")
        batch.drop_column("resource_type")
        batch.drop_column("actor_user_id")

    op.drop_index(op.f("ix_users_role_id"), table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_role_id", type_="foreignkey")
        batch.drop_column("last_login_at")
        batch.drop_column("updated_at")
        batch.drop_column("email_verified")
        batch.drop_column("avatar_url")
        batch.drop_column("phone")
        batch.drop_column("full_name")
        batch.drop_column("role_id")

    op.drop_index(op.f("ix_password_resets_user_id"), table_name="password_resets")
    op.drop_index(op.f("ix_password_resets_token_hash"), table_name="password_resets")
    op.drop_table("password_resets")

    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_jti"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_created_at"), table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index(op.f("ix_role_permissions_role_id"), table_name="role_permissions")
    op.drop_index(op.f("ix_role_permissions_permission_id"), table_name="role_permissions")
    op.drop_table("role_permissions")

    op.drop_index(op.f("ix_permissions_code"), table_name="permissions")
    op.drop_table("permissions")

    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
