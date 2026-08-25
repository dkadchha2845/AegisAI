"""
The evidence store's tables — task 1.5, ARCHITECTURE.md §7 and §8.

**Why it exists.** Until now an investigation existed only in memory: the graph
in 1.3 returned an `InvestigationState` to its caller and nothing wrote it down.
That is fine for a demo and useless for everything else — a report cannot be
re-opened, a crashed worker loses the work, the Phase 3 graph has no history to
build a network from, and the Phase 9 ablations have nothing to replay against.
These six tables are where an investigation becomes a durable fact.

**What it consumes.** `schema.models.InvestigationState` and nothing else. The
tables are a persistence projection of the contract, never a second definition
of it: no column exists here that the contract does not have a field for.

**What it outputs.** Rows that `evidence.EvidenceStore` reassembles into exactly
the state that was saved.

**How it connects.** `evidence.EvidenceStore` is the only module that reads or
writes these tables; 1.6's lifecycle API goes through it, and Phase 3's graph
loader reads `entities` / `case_entities` to find the cases an identifier
appears in. Nothing imports these classes to build its own query — that is the
point of putting tenant scoping in the repository.

**How it is evaluated.** `test_evidence_store.py`: a fully populated state round
trips byte-identically, every agent result and finding is re-readable on its
own, a second organisation cannot see any of it, and the Alembic head produces
exactly this metadata with no diff.

**Limitations, stated.** `EvidenceItem.uri` points at `stores/blobs.py`, a
directory on a local disk — durable, and not a replicated object store, so two
API replicas do not share it. `entities` deduplicates *within* an
organisation only; the cross-organisation linkage that makes a fraud network is
Module 2's graph store, deliberately not this one — see the note on
`EntityRecord`. And nothing here is encrypted at rest: that is a deployment
concern (volume encryption) rather than a column type, and claiming otherwise
in a docstring would be the kind of unmeasured security claim CLAUDE.md forbids.

Why a residual JSON column exists
---------------------------------
`InvestigationState` has twenty-nine fields. Six tables cover the ones that have
to be queried, joined or counted — identity, evidence items, agent results,
findings, entities. The rest (`trace`, `rag_context`, `graph_context`,
`risk_features`, …) are read back whole, with the case, and never on their own.
Giving each of them a table would be a dozen more joins bought with no query
anyone would run.

So they go in one `rest` column, and the rule is mechanical: `rest` is the state
minus everything a column or a table already holds. Nothing is stored twice, so
the two cannot disagree, and a field added to the contract tomorrow is carried
without a migration instead of being silently dropped —
`test_evidence_store.py::test_residual_covers_every_contract_field` is what
keeps that true, and fails loudly when a new field deserves a column instead.

JSON on SQLite, JSONB on PostgreSQL
-----------------------------------
`_JSON` is one type with a dialect variant. SQLite gets `JSON` (text with a
JSON-aware accessor); PostgreSQL gets real `JSONB`, which is what §7 chose it
for — binary, indexable, and queryable with `->>` so "every case whose agent
results mention urlhaus" is an index scan rather than a full-table parse.
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

#: JSONB where the deployment has it, plain JSON where it does not. One column
#: type, two storage engines, no branch in the repository.
_JSON = JSON().with_variant(JSONB(), "postgresql")

#: Widths. Deliberately generous but bounded, because an unbounded identifier
#: column is a place to put a megabyte of attacker-supplied text. Values longer
#: than the column are the caller's error, not something to silently truncate.
_ID = 64
_ORG = 64
_ENUM = 32


def _utcnow() -> _dt.datetime:
    """Naive UTC, the same convention as `models_db._utcnow`.

    Not the contract's timestamps — those are ISO-8601 strings and are stored
    verbatim as strings (see `Investigation.created_at`). This is only for the
    store's own bookkeeping: when *we* wrote the row, which is a different fact
    from when the investigation happened and is what a retention policy acts on.
    """
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


class Investigation(Base):
    """One investigation. The root every other table hangs off.

    `case_id` is unique **per organisation**, not globally. Two tenants
    generating the same case id is not a collision to be resolved, it is two
    unrelated cases, and a global unique constraint would let one org's write
    fail because of a case it is not allowed to know exists.

    Timestamps from the contract (`created_at`, `completed_at`) are stored as
    the ISO-8601 UTC strings they are on the wire, not parsed into `DateTime`.
    That is the same decision `schema.models.utc_now_iso` documents: a string
    that always ends in `Z` has one representation and survives the round trip
    identically, and this project has been bitten twice by naive-versus-aware
    datetimes. Lexicographic ordering on fixed-width ISO-8601 UTC is also
    chronological, so `ORDER BY created_at` is still correct.
    """

    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: The tenant. On every table in this store, never nullable — see the
    #: module docstring of `evidence.py` for why that is the whole design.
    org_id: Mapped[str] = mapped_column(String(_ORG), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(_ID), nullable=False, index=True)

    #: `InvestigationState.v` — which contract version wrote this row. A state
    #: read back years later says which shape it was written in.
    contract_v: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_by: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    completed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mode: Mapped[str] = mapped_column(String(_ENUM), nullable=False, default="batch")
    status: Mapped[str] = mapped_column(String(_ENUM), nullable=False, index=True)

    #: The judgement, lifted out of `rest` because these are the four things a
    #: case list sorts and filters on. `risk_score` stays nullable: an
    #: unfinished investigation must not read as 0.0/CALM, which is a false
    #: negative wearing a number.
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    risk_level: Mapped[str | None] = mapped_column(String(_ENUM), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(_ENUM), nullable=True, index=True)

    #: Everything the contract carries that no column or table above holds.
    rest: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)

    stored_at: Mapped[_dt.datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("org_id", "case_id", name="uq_investigations_org_case"),
        Index("ix_investigations_org_created", "org_id", "created_at"),
    )


class EvidenceItemRow(Base):
    """One submitted artefact — `InvestigationState.inputs[i]`.

    `ordinal` exists because the contract's `inputs` is a list and a list has an
    order. Rebuilding by primary key would usually give the same order and
    occasionally not, and "usually deterministic" is the failure mode 1.3 spent
    a whole determinism module avoiding.

    `declared_type` and `media_type` are both kept, exactly as the contract
    keeps them: what the uploader claimed and what the magic bytes said. Their
    disagreement is the finding, and it can only be a finding if the lie is
    written down.
    """

    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Denormalised from the parent so that *every* table in this store can be
    #: filtered by tenant without a join. A join is one refactor away from being
    #: dropped; a column on the row is not.
    org_id: Mapped[str] = mapped_column(String(_ORG), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    item_id: Mapped[str] = mapped_column(String(_ID), nullable=False)
    kind: Mapped[str] = mapped_column(String(_ENUM), nullable=False, default="UNKNOWN", index=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    declared_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Hex sha256 of the artefact — 64 characters, the chain-of-custody handle.
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("investigation_id", "item_id", name="uq_evidence_items_case_item"),
    )


class AgentResultRow(Base):
    """One agent execution — `InvestigationState.agent_results[i]`.

    The columns are the fields Phase 9 aggregates over: per-agent success rate
    needs `agent`/`status`, the p95 latency table needs `latency_ms`, and
    inter-agent disagreement needs `confidence`. Everything else the contract
    carries (`features`, `provenance`) rides in `payload`, because nothing
    queries it and a `features` table would be one row per float.

    `findings` is deliberately *not* in `payload`: it is its own table below, so
    a finding is addressable on its own. Storing it in both places would create
    two answers to "what did this agent observe".
    """

    __tablename__ = "agent_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(String(_ORG), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    agent: Mapped[str] = mapped_column(String(_ID), nullable=False, index=True)
    #: Pinned per ARCHITECTURE.md §3 — a result recorded a year ago says which
    #: code produced it, which is what makes the Phase 9 ablations replayable.
    version: Mapped[str] = mapped_column(String(_ENUM), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(_ENUM), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: `features` and `provenance`.
    payload: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_agent_results_org_agent", "org_id", "agent"),
    )


class FindingRow(Base):
    """One machine-facing observation — `AgentResult.findings[i]`.

    Its own table so that `label` is indexable. "Every case this quarter where
    `domain_age_days` was under 30" is the query the Phase 9 evaluation and the
    Phase 3 graph both want, and it is an index scan here and a full-table JSON
    parse if findings live inside the agent result blob.

    This is `schema.models.Finding`, not `EvidenceFinding`. The contract keeps
    those two apart on purpose — an agent emits many small findings, and the
    handful promoted to a citizen-facing report are a different type with a
    different lifetime. The promoted ones ride in `Investigation.rest` until a
    report table has a reason to exist.
    """

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_result_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Also linked straight to the case, so "the findings for this case" does
    #: not need a join through agent_results, and so the cascade has two
    #: independent paths to the same row.
    investigation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(String(_ORG), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    label: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_findings_org_label", "org_id", "label"),
    )


class EntityRecord(Base):
    """One identifier, once per organisation — the rows `case_entities` joins.

    `kind` is the `EntitySet` field name verbatim (`phones`, `upi_ids`, …).
    Matching the contract's own names is the same hard requirement the contract
    states for `EntitySet` itself: a store that said `accounts` where the
    contract says `bank_accounts` would drop a whole entity class at the
    boundary, silently, in Phase 3.

    **`linkable` is a safety property, not metadata.** The contract names ten
    fields whose sharing means two cases are connected, and says plainly that
    `banks`, `locations` and `scam_keywords` must never become graph edges —
    two cases both naming "SBI" are not related by that fact. Recording the
    distinction on the row means Phase 3 cannot accidentally build an edge out
    of a common noun, because the row it would need says it may not.
    `amounts` and `authorities` are marked unlinkable for the same reason
    stated the other way round: the contract warrants ten, so ten is what this
    store is willing to call linkable.

    **Scoped to one organisation, on purpose.** Every row in this store carries
    `org_id` and that has exactly no exceptions, which is what makes the
    isolation claim checkable in one line rather than defensible in a paragraph.
    Cross-tenant linkage — the shared national intelligence that makes a fraud
    *network* — is Module 2's graph, a separate store with a separate and
    deliberately different policy (see `models_db.Organization`). Putting a
    cross-org read in the evidence store to save Phase 3 a lookup would mean
    this store has one rule and one exception, and exceptions are where
    isolation bugs live.

    `value_hash` rather than a unique index on `value` because a phishing URL is
    routinely longer than the ~2700-byte limit of a PostgreSQL btree entry.
    Hashing the exact bytes keeps the constraint exact and unbounded.

    The value is stored **exactly as extracted**, uncanonicalised. Lowercasing a
    domain or stripping a handle is a judgement about what two identifiers mean,
    which belongs to the graph that reasons about identity — an evidence store
    that quietly rewrites evidence is not an evidence store.
    """

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[str] = mapped_column(String(_ORG), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(_ENUM), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    #: sha256 of `value`, so the uniqueness constraint has a bounded key.
    value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    linkable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen: Mapped[_dt.datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    last_seen: Mapped[_dt.datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("org_id", "kind", "value_hash", name="uq_entities_org_kind_value"),
        Index("ix_entities_org_kind", "org_id", "kind"),
    )


class CaseEntity(Base):
    """An investigation mentioned an entity. The many-to-many, and the only
    table in this store whose *rows* are the evidence rather than its columns.

    This is what Phase 3 reads to find the cases an identifier appears in, and
    it is what makes `GraphContext.prior_case_ids` a query instead of a scan.

    `ordinal` preserves the position the value had in its `EntitySet` list, so
    a state reassembled from rows has its entity lists in the order the
    extractor produced them rather than in insertion order. The extractors are
    deterministic; the store must not be the thing that stops being.
    """

    __tablename__ = "case_entities"

    investigation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("investigations.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    org_id: Mapped[str] = mapped_column(String(_ORG), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


#: Every table this store owns, in dependency order. Used by the repository's
#: delete path and by the test that asserts the isolation rule holds on all of
#: them — a new table added without `org_id` fails that test rather than
#: quietly becoming the one place a tenant boundary does not exist.
EVIDENCE_TABLES = (
    Investigation,
    EvidenceItemRow,
    AgentResultRow,
    FindingRow,
    EntityRecord,
    CaseEntity,
)

__all__ = [
    "EVIDENCE_TABLES",
    "AgentResultRow",
    "CaseEntity",
    "EntityRecord",
    "EvidenceItemRow",
    "FindingRow",
    "Investigation",
]
