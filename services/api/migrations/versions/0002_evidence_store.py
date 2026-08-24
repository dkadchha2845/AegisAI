"""Evidence store: investigations, evidence items, agent results, findings, entities.

Task 1.5. Six tables that turn an investigation from an object the graph
returned into a durable record — see `services/api/stores/models.py` for what
each one is for and why the split falls where it does.

`rest` and `payload` are `JSONB` on PostgreSQL and `JSON` on SQLite, from one
column type with a dialect variant. That is the §7 rationale for choosing
PostgreSQL made concrete: the same code stores agent output as indexable binary
JSON on the real store and as JSON-typed text on the zero-setup fallback.

Revision ID: 0002
Revises: 0001
Created: 2026-08-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Must stay identical to `stores/models._JSON`. `test_migrations.py` compares
#: the migrated schema against `Base.metadata` with `compare_type=True`, so a
#: divergence here fails rather than becoming a column nobody notices is wrong.
_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("contract_v", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("completed_at", sa.String(length=32), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("classification", sa.String(length=32), nullable=True),
        sa.Column("rest", _JSON, nullable=False),
        sa.Column("stored_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # Per organisation, not global: two tenants minting the same case id are
        # two unrelated cases, and a global constraint would let one org's write
        # fail because of a case it may not know exists.
        sa.UniqueConstraint("org_id", "case_id", name="uq_investigations_org_case"),
    )
    op.create_index(op.f("ix_investigations_case_id"), "investigations", ["case_id"])
    op.create_index(op.f("ix_investigations_classification"), "investigations", ["classification"])
    op.create_index(op.f("ix_investigations_created_at"), "investigations", ["created_at"])
    op.create_index("ix_investigations_org_created", "investigations", ["org_id", "created_at"])
    op.create_index(op.f("ix_investigations_org_id"), "investigations", ["org_id"])
    op.create_index(op.f("ix_investigations_risk_level"), "investigations", ["risk_level"])
    op.create_index(op.f("ix_investigations_risk_score"), "investigations", ["risk_score"])
    op.create_index(op.f("ix_investigations_status"), "investigations", ["status"])

    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_hash", sa.String(length=64), nullable=False),
        sa.Column("linkable", sa.Boolean(), nullable=False),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "kind", "value_hash", name="uq_entities_org_kind_value"),
    )
    op.create_index(op.f("ix_entities_kind"), "entities", ["kind"])
    op.create_index(op.f("ix_entities_org_id"), "entities", ["org_id"])
    op.create_index("ix_entities_org_kind", "entities", ["org_id", "kind"])

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("investigation_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("declared_type", sa.String(length=128), nullable=True),
        sa.Column("media_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("received_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("investigation_id", "item_id", name="uq_evidence_items_case_item"),
    )
    op.create_index(
        op.f("ix_evidence_items_investigation_id"), "evidence_items", ["investigation_id"]
    )
    op.create_index(op.f("ix_evidence_items_kind"), "evidence_items", ["kind"])
    op.create_index(op.f("ix_evidence_items_org_id"), "evidence_items", ["org_id"])
    op.create_index(op.f("ix_evidence_items_sha256"), "evidence_items", ["sha256"])

    op.create_table(
        "agent_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("investigation_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", _JSON, nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_results_agent"), "agent_results", ["agent"])
    op.create_index(
        op.f("ix_agent_results_investigation_id"), "agent_results", ["investigation_id"]
    )
    op.create_index("ix_agent_results_org_agent", "agent_results", ["org_id", "agent"])
    op.create_index(op.f("ix_agent_results_org_id"), "agent_results", ["org_id"])
    op.create_index(op.f("ix_agent_results_status"), "agent_results", ["status"])

    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_result_id", sa.Integer(), nullable=False),
        sa.Column("investigation_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["agent_result_id"], ["agent_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_findings_agent_result_id"), "findings", ["agent_result_id"])
    op.create_index(op.f("ix_findings_investigation_id"), "findings", ["investigation_id"])
    op.create_index(op.f("ix_findings_label"), "findings", ["label"])
    op.create_index(op.f("ix_findings_org_id"), "findings", ["org_id"])
    op.create_index("ix_findings_org_label", "findings", ["org_id", "label"])

    op.create_table(
        "case_entities",
        sa.Column("investigation_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("investigation_id", "entity_id"),
    )
    op.create_index(op.f("ix_case_entities_org_id"), "case_entities", ["org_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_case_entities_org_id"), table_name="case_entities")
    op.drop_table("case_entities")

    op.drop_index("ix_findings_org_label", table_name="findings")
    op.drop_index(op.f("ix_findings_org_id"), table_name="findings")
    op.drop_index(op.f("ix_findings_label"), table_name="findings")
    op.drop_index(op.f("ix_findings_investigation_id"), table_name="findings")
    op.drop_index(op.f("ix_findings_agent_result_id"), table_name="findings")
    op.drop_table("findings")

    op.drop_index(op.f("ix_agent_results_status"), table_name="agent_results")
    op.drop_index(op.f("ix_agent_results_org_id"), table_name="agent_results")
    op.drop_index("ix_agent_results_org_agent", table_name="agent_results")
    op.drop_index(op.f("ix_agent_results_investigation_id"), table_name="agent_results")
    op.drop_index(op.f("ix_agent_results_agent"), table_name="agent_results")
    op.drop_table("agent_results")

    op.drop_index(op.f("ix_evidence_items_sha256"), table_name="evidence_items")
    op.drop_index(op.f("ix_evidence_items_org_id"), table_name="evidence_items")
    op.drop_index(op.f("ix_evidence_items_kind"), table_name="evidence_items")
    op.drop_index(op.f("ix_evidence_items_investigation_id"), table_name="evidence_items")
    op.drop_table("evidence_items")

    op.drop_index("ix_entities_org_kind", table_name="entities")
    op.drop_index(op.f("ix_entities_org_id"), table_name="entities")
    op.drop_index(op.f("ix_entities_kind"), table_name="entities")
    op.drop_table("entities")

    op.drop_index(op.f("ix_investigations_status"), table_name="investigations")
    op.drop_index(op.f("ix_investigations_risk_score"), table_name="investigations")
    op.drop_index(op.f("ix_investigations_risk_level"), table_name="investigations")
    op.drop_index(op.f("ix_investigations_org_id"), table_name="investigations")
    op.drop_index("ix_investigations_org_created", table_name="investigations")
    op.drop_index(op.f("ix_investigations_created_at"), table_name="investigations")
    op.drop_index(op.f("ix_investigations_classification"), table_name="investigations")
    op.drop_index(op.f("ix_investigations_case_id"), table_name="investigations")
    op.drop_table("investigations")
