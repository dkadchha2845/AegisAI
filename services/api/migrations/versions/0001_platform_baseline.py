"""Platform baseline: organisations, users, saved cases, citizen reports, audit.

These five tables predate Alembic — they were created by
`Base.metadata.create_all` since Phase 0. This revision is their baseline, so a
database managed by migrations from here on has one complete history rather than
starting half-formed.

An existing database built by `create_all` must be stamped rather than upgraded:

    alembic -x url=sqlite:///aegis.db stamp 0001

Running `upgrade` against it instead fails on the first `CREATE TABLE`, which is
the correct and loud failure — silently skipping tables that already exist is
how a schema and its migration history stop agreeing.

Revision ID: 0001
Revises:
Created: 2026-08-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_org_id"), "users", ["org_id"], unique=False)

    op.create_table(
        "case_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=True),
        sa.Column("caller_number", sa.String(length=64), nullable=True),
        sa.Column("incident_type", sa.String(length=200), nullable=True),
        sa.Column("peak_threat", sa.Float(), nullable=True),
        sa.Column("final_level", sa.String(length=16), nullable=True),
        sa.Column("package_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_case_records_org_id"), "case_records", ["org_id"], unique=False)
    op.create_index(op.f("ix_case_records_report_id"), "case_records", ["report_id"], unique=True)
    op.create_index(
        op.f("ix_case_records_session_id"), "case_records", ["session_id"], unique=False
    )

    op.create_table(
        "citizen_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("city", sa.String(length=80), nullable=True),
        sa.Column("caller_number", sa.String(length=64), nullable=True),
        sa.Column("upi_id", sa.String(length=128), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("scam_stage", sa.String(length=32), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_citizen_reports_token"), "citizen_reports", ["token"], unique=True)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=200), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"], unique=False)
    op.create_index(op.f("ix_audit_events_org_id"), "audit_events", ["org_id"], unique=False)
    op.create_index(op.f("ix_audit_events_ts"), "audit_events", ["ts"], unique=False)


def downgrade() -> None:
    # Reverse creation order: every table that references `organizations` goes
    # first, or the drop fails on a database that enforces its foreign keys.
    op.drop_index(op.f("ix_audit_events_ts"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_org_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(op.f("ix_citizen_reports_token"), table_name="citizen_reports")
    op.drop_table("citizen_reports")

    op.drop_index(op.f("ix_case_records_session_id"), table_name="case_records")
    op.drop_index(op.f("ix_case_records_report_id"), table_name="case_records")
    op.drop_index(op.f("ix_case_records_org_id"), table_name="case_records")
    op.drop_table("case_records")

    op.drop_index(op.f("ix_users_org_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")
