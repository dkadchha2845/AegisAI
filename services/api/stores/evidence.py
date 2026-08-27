"""
The evidence repository — task 1.5. Tenant isolation lives here, and only here.

**Why it exists.** ARCHITECTURE.md §8 puts `org_id` enforcement in the
repository layer rather than in the route, and CLAUDE.md repeats it as an
invariant. The reason is a difference in failure mode: *a route that forgets to
scope a query is a bug; a repository that cannot express an unscoped query is a
design.* This class is that design. The organisation is bound at construction,
every query filters on it, and no method takes an organisation argument — so
forgetting to scope is not a mistake a caller is able to make.

**What it consumes.** A SQLAlchemy `Session` and one `org_id`, then whole
`InvestigationState` objects.

**What it outputs.** `InvestigationState` again, reassembled from rows — plus
the narrower reads (agent results, findings, the cases an identifier appears in)
that exist so callers do not have to load a whole case to answer a small
question.

**How it connects.** The lifecycle API (1.6) saves through `save()`, serves
`GET /api/investigations/{id}` from `load()`, and erases through
`delete_case()`. 1.8's worker will save from outside the request path. Phase 3's
graph builder reads `cases_for_entity()`. The tables
themselves are in `stores/models.py`, and nothing outside this module queries
them.

**How it is evaluated.** `test_evidence_store.py`: a fully populated state round
trips equal to itself, agent results and findings are separately re-readable,
two organisations holding the same `case_id` never see each other's rows, and
the store refuses to write a state whose `org_id` is not its own.

**Limitations, stated.** Entity upsert is one `SELECT` per distinct identifier
rather than a dialect-specific `INSERT … ON CONFLICT`; at a few dozen entities
per case that is not worth two code paths, and it is the first thing to change
if a bulk backfill ever gets slow. `save()` rewrites a case's child rows rather
than diffing them, which is correct and simple but makes an update cost the
same as an insert. There is no row-level security in the database itself — the
isolation is this class, so a second module that queried `models.py` directly
would bypass it, which is why `test_evidence_store.py` also asserts that no
other module imports those tables.

On SQLite, cascade is not the delete mechanism
----------------------------------------------
The foreign keys declare `ON DELETE CASCADE`, and PostgreSQL honours them.
SQLite does not, unless `PRAGMA foreign_keys=ON` is issued on every connection —
off by default, per-connection, and easy to lose to a pool change. Deleting a
case is the erasure path `DELETE /api/investigations/{id}` exposes to a citizen
exercising a right, so it may not depend on a database setting that can
silently be off. `delete_case()`
deletes children explicitly, in dependency order. The cascade stays declared
because it is correct, and is a backstop for anything that ever deletes a parent
row outside this class — not the thing the erasure claim rests on.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional, get_args

from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import Session

from schema.models import (
    AgentResult,
    EntitySet,
    Finding,
    InvestigationState,
)

from .models import (
    AgentResultRow,
    CaseEntity,
    EntityRecord,
    EvidenceItemRow,
    FindingRow,
    Investigation,
    _utcnow,
)

#: The `EntitySet` fields whose sharing means two cases are connected. Copied
#: from the contract's own docstring, which names exactly these ten and then
#: says the remainder must never become graph edges. Anything not listed here
#: is stored with `linkable=False`; see `models.EntityRecord` for why the
#: conservative direction is the correct one.
LINKABLE_ENTITY_FIELDS: frozenset[str] = frozenset(
    {
        "phones",
        "upi_ids",
        "emails",
        "wallets",
        "bank_accounts",
        "domains",
        "urls",
        "ips",
        "apps",
        "orgs",
    }
)

#: Contract fields that `Investigation` holds in a column of its own.
_COLUMN_FIELDS: frozenset[str] = frozenset(
    {
        "v",
        "case_id",
        "org_id",
        "created_by",
        "created_at",
        "completed_at",
        "mode",
        "status",
        "risk_score",
        "risk_level",
        "confidence",
        "classification",
    }
)

#: Contract fields that a table of their own holds.
_TABLE_FIELDS: frozenset[str] = frozenset({"inputs", "agent_results", "entities"})

#: Everything above. What is left of `InvestigationState` after removing these
#: is what goes in `Investigation.rest`, and the partition is exhaustive by
#: construction — there is no third place a field can go, and nothing can be in
#: two places at once.
STORED_OUTSIDE_REST: frozenset[str] = _COLUMN_FIELDS | _TABLE_FIELDS


def _entity_field_types() -> dict[str, type]:
    """The element type of every `EntitySet` list, read off the contract.

    `amounts` is `list[float]` and everything else is `list[str]`. Deriving it
    rather than hard-coding the exception means a future numeric entity field
    round trips correctly without anyone remembering this function exists.
    """
    types: dict[str, type] = {}
    for name, field in EntitySet.model_fields.items():
        args = get_args(field.annotation)
        types[name] = args[0] if args and isinstance(args[0], type) else str
    return types


_ENTITY_TYPES: dict[str, type] = _entity_field_types()


def _hash(value: str) -> str:
    """Uniqueness key for an entity value. sha256 of the exact bytes.

    Not a security boundary — a bounded index key for an unbounded value, so a
    900-character phishing URL is still subject to the unique constraint that a
    btree could not otherwise hold.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OrgMismatch(ValueError):
    """Raised when a store is asked to write a state belonging to another org.

    A distinct type rather than a bare `ValueError` because 1.6 has to turn this
    into a 403 and must not have to match on a message string. It is a
    programming error, not a user error: a route that produced it is passing a
    state it was never given the right to persist.
    """


class EvidenceStore:
    """Durable investigations for one organisation.

    Construct one per request, with the session and the caller's org. There is
    deliberately no method that takes an `org_id`, no `load_any()`, and no
    escape hatch for a platform superadmin — an exception to a tenancy rule is
    where the isolation bug eventually lives, and the owner-level cross-org view
    can be built the day it is actually needed, out of a query that says so.
    """

    def __init__(self, db: Session, org_id: str) -> None:
        if not org_id or not org_id.strip():
            # An empty scope would filter to nothing and read as "no cases",
            # which is indistinguishable from a real empty tenant. Failing here
            # means the missing org surfaces where it was dropped.
            raise ValueError("EvidenceStore requires a non-empty org_id")
        self.db = db
        self.org_id = org_id

    # -- writes ------------------------------------------------------------

    def save(self, state: InvestigationState) -> int:
        """Persist one investigation, replacing any earlier revision of it.

        One investigation is one transaction: an investigation half-written is
        worse than one not written, because the case list would show it and the
        report would be missing its agent results. Returns the row id.
        """
        if state.org_id != self.org_id:
            raise OrgMismatch(
                f"store is scoped to org {self.org_id!r}; "
                f"state {state.case_id!r} belongs to {state.org_id!r}"
            )

        row = self._case_row(state.case_id)
        if row is None:
            row = Investigation(org_id=self.org_id, case_id=state.case_id)
            self.db.add(row)

        row.contract_v = state.v
        row.created_by = state.created_by
        row.created_at = state.created_at
        row.completed_at = state.completed_at
        row.mode = state.mode
        row.status = state.status.value
        row.risk_score = state.risk_score
        row.risk_level = state.risk_level.value if state.risk_level else None
        row.confidence = state.confidence
        row.classification = state.classification.value if state.classification else None
        row.rest = _residual(state)
        row.updated_at = _utcnow()

        self.db.flush()  # assigns row.id for the children below
        self._clear_children(row.id)

        for i, item in enumerate(state.inputs):
            self.db.add(
                EvidenceItemRow(
                    investigation_id=row.id,
                    org_id=self.org_id,
                    ordinal=i,
                    item_id=item.id,
                    kind=item.kind.value,
                    filename=item.filename,
                    declared_type=item.declared_type,
                    media_type=item.media_type,
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                    uri=item.uri,
                    text=item.text,
                    received_at=item.received_at,
                )
            )

        for i, result in enumerate(state.agent_results):
            ar = AgentResultRow(
                investigation_id=row.id,
                org_id=self.org_id,
                ordinal=i,
                agent=result.agent,
                version=result.version,
                status=result.status.value,
                confidence=result.confidence,
                latency_ms=result.latency_ms,
                error=result.error,
                payload={"features": result.features, "provenance": result.provenance},
            )
            self.db.add(ar)
            self.db.flush()  # ar.id, needed by its findings
            for j, finding in enumerate(result.findings):
                self.db.add(
                    FindingRow(
                        agent_result_id=ar.id,
                        investigation_id=row.id,
                        org_id=self.org_id,
                        ordinal=j,
                        label=finding.label,
                        value=finding.value,
                        confidence=finding.confidence,
                        source=finding.source,
                        detail=finding.detail,
                    )
                )

        self._save_entities(row.id, state.entities)
        self.db.commit()
        return int(row.id)

    def delete_case(self, case_id: str) -> bool:
        """Erase one investigation and everything hanging off it.

        Children are deleted explicitly rather than by cascade — see the module
        docstring. Entities left referenced by no remaining case are removed
        too: an identifier that survives the only case that mentioned it is a
        record of a case that was supposed to be gone.

        Returns False if this organisation has no such case, which is also the
        answer when another organisation does.
        """
        row = self._case_row(case_id)
        if row is None:
            return False
        entity_ids = [
            e_id
            for (e_id,) in self.db.query(CaseEntity.entity_id).filter(
                CaseEntity.investigation_id == row.id,
                CaseEntity.org_id == self.org_id,
            )
        ]
        self._clear_children(row.id)
        self.db.delete(row)
        self.db.flush()
        self._prune_orphan_entities(entity_ids)
        self.db.commit()
        return True

    # -- reads -------------------------------------------------------------

    def load(self, case_id: str) -> Optional[InvestigationState]:
        """Rebuild the full state, or None if this organisation has no such case.

        Reassembled from rows, not from a stored copy of the whole state. That
        is the point of the acceptance criterion: if the state came back out of
        a single blob, the six tables would be decoration and the round-trip
        test would prove nothing about them.
        """
        row = self._case_row(case_id)
        if row is None:
            return None

        payload: dict[str, Any] = dict(row.rest or {})
        payload.update(
            {
                "v": row.contract_v,
                "case_id": row.case_id,
                "org_id": row.org_id,
                "created_by": row.created_by,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
                "mode": row.mode,
                "status": row.status,
                "risk_score": row.risk_score,
                "risk_level": row.risk_level,
                "confidence": row.confidence,
                "classification": row.classification,
                "inputs": [_to_evidence_item(r) for r in self._evidence_rows(row.id)],
                "agent_results": [r.model_dump() for r in self._agent_results(row.id)],
                "entities": _to_entity_set(self._entity_rows(row.id)).model_dump(),
            }
        )
        return InvestigationState.model_validate(payload)

    def exists(self, case_id: str) -> bool:
        return self._case_row(case_id) is not None

    def count(self, *, created_by: Optional[str] = None) -> int:
        """How many investigations this organisation has. Never anyone else's.

        `created_by` narrows further, to the cases one person submitted — the
        count beside a citizen's own case list. It is a filter on the query for
        the same reason `list_cases`'s is: a total computed by counting rows
        the caller may not see is a total that leaks how many there are.
        """
        q = self.db.query(Investigation).filter(Investigation.org_id == self.org_id)
        if created_by:
            q = q.filter(Investigation.created_by == created_by)
        return int(q.count())

    def list_cases(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Summaries for a case list, newest first.

        Deliberately not `list[InvestigationState]`: a case list that loads every
        agent result and trace span to render twelve rows is the kind of thing
        that is fine in a demo and unusable at a thousand cases.

        `created_by` is the ownership narrowing a caller with only
        `INVESTIGATION_READ_OWN` gets. It lives here, in the one class that owns
        every query against these tables, rather than in the route — the same
        reason `org_id` does.
        """
        q = self.db.query(Investigation).filter(Investigation.org_id == self.org_id)
        if status:
            q = q.filter(Investigation.status == status)
        if created_by:
            q = q.filter(Investigation.created_by == created_by)
        rows = (
            q.order_by(Investigation.created_at.desc(), Investigation.id.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
            .all()
        )
        return [_summary(r) for r in rows]

    def agent_results(self, case_id: str) -> list[AgentResult]:
        """Every agent result for one case, in the order the graph merged them.

        Re-readable on its own, without rebuilding the state — the acceptance
        criterion, and what an agent-timing panel actually needs.
        """
        row = self._case_row(case_id)
        if row is None:
            return []
        return self._agent_results(row.id)

    def findings(
        self, *, case_id: Optional[str] = None, label: Optional[str] = None, limit: int = 500
    ) -> list[Finding]:
        """Findings across this organisation, optionally narrowed to one case
        or one label. This is the query `findings` has its own table for."""
        q = self.db.query(FindingRow).filter(FindingRow.org_id == self.org_id)
        if case_id is not None:
            row = self._case_row(case_id)
            if row is None:
                return []
            q = q.filter(FindingRow.investigation_id == row.id)
        if label is not None:
            q = q.filter(FindingRow.label == label)
        rows = (
            q.order_by(FindingRow.investigation_id, FindingRow.agent_result_id, FindingRow.ordinal)
            .limit(max(1, min(limit, 5000)))
            .all()
        )
        return [
            Finding(
                label=r.label,
                value=r.value,
                confidence=r.confidence,
                source=r.source,
                detail=r.detail,
            )
            for r in rows
        ]

    def cases_for_entity(self, kind: str, value: str) -> list[str]:
        """Which of this organisation's cases mentioned this identifier.

        What `GraphContext.prior_case_ids` is built from in Phase 3, and the
        reason `case_entities` exists at all. Ordered by case id so two calls
        agree.
        """
        rows = (
            self.db.query(Investigation.case_id)
            .join(CaseEntity, CaseEntity.investigation_id == Investigation.id)
            .join(EntityRecord, EntityRecord.id == CaseEntity.entity_id)
            .filter(
                Investigation.org_id == self.org_id,
                EntityRecord.org_id == self.org_id,
                EntityRecord.kind == kind,
                EntityRecord.value_hash == _hash(value),
            )
            .distinct()
            .order_by(Investigation.case_id)
            .all()
        )
        return [c for (c,) in rows]

    # -- internals ---------------------------------------------------------

    def _case_row(self, case_id: str) -> Optional[Investigation]:
        """The single place a case is looked up. Scoped, with no override."""
        return (
            self.db.query(Investigation)
            .filter(Investigation.org_id == self.org_id, Investigation.case_id == case_id)
            .one_or_none()
        )

    def _clear_children(self, investigation_id: int) -> None:
        """Drop every child row of one case, in dependency order.

        `org_id` is on the filter as well as `investigation_id`, which is
        redundant given the parent lookup was already scoped — deliberately so.
        The redundancy costs nothing and means a future caller that reaches this
        with an id from somewhere else still cannot touch another tenant's rows.
        """
        for table in (FindingRow, AgentResultRow, EvidenceItemRow, CaseEntity):
            self.db.execute(
                sa_delete(table).where(
                    table.investigation_id == investigation_id,
                    table.org_id == self.org_id,
                )
            )
        self.db.flush()

    def _save_entities(self, investigation_id: int, entities: EntitySet) -> None:
        """Upsert every identifier, then link each to this case.

        Duplicates within one list collapse to one row and keep their first
        position. The contract already describes `EntitySet` as deduplicated, so
        this is defensive rather than expected — but a repeated value would
        otherwise violate the join's primary key and fail the whole save, and
        losing an investigation to a duplicated phone number is not a trade
        anyone would choose.
        """
        now = _utcnow()
        seen: set[tuple[str, str]] = set()
        for kind, value, ordinal in _entity_pairs(entities):
            key = (kind, value)
            if key in seen:
                continue
            seen.add(key)

            digest = _hash(value)
            record = (
                self.db.query(EntityRecord)
                .filter(
                    EntityRecord.org_id == self.org_id,
                    EntityRecord.kind == kind,
                    EntityRecord.value_hash == digest,
                )
                .one_or_none()
            )
            if record is None:
                record = EntityRecord(
                    org_id=self.org_id,
                    kind=kind,
                    value=value,
                    value_hash=digest,
                    linkable=kind in LINKABLE_ENTITY_FIELDS,
                    first_seen=now,
                    last_seen=now,
                )
                self.db.add(record)
                self.db.flush()
            else:
                record.last_seen = now

            self.db.add(
                CaseEntity(
                    investigation_id=investigation_id,
                    entity_id=record.id,
                    org_id=self.org_id,
                    ordinal=ordinal,
                )
            )
        self.db.flush()

    def _prune_orphan_entities(self, entity_ids: list[int]) -> None:
        """Remove entities no remaining case of this organisation mentions."""
        for entity_id in entity_ids:
            still_used = (
                self.db.query(CaseEntity)
                .filter(CaseEntity.entity_id == entity_id, CaseEntity.org_id == self.org_id)
                .first()
            )
            if still_used is None:
                self.db.execute(
                    sa_delete(EntityRecord).where(
                        EntityRecord.id == entity_id,
                        EntityRecord.org_id == self.org_id,
                    )
                )
        self.db.flush()

    def _evidence_rows(self, investigation_id: int) -> list[EvidenceItemRow]:
        return (
            self.db.query(EvidenceItemRow)
            .filter(
                EvidenceItemRow.investigation_id == investigation_id,
                EvidenceItemRow.org_id == self.org_id,
            )
            .order_by(EvidenceItemRow.ordinal)
            .all()
        )

    def _entity_rows(self, investigation_id: int) -> list[tuple[EntityRecord, int]]:
        rows = (
            self.db.query(EntityRecord, CaseEntity.ordinal)
            .join(CaseEntity, CaseEntity.entity_id == EntityRecord.id)
            .filter(
                CaseEntity.investigation_id == investigation_id,
                CaseEntity.org_id == self.org_id,
                EntityRecord.org_id == self.org_id,
            )
            .order_by(EntityRecord.kind, CaseEntity.ordinal)
            .all()
        )
        return [(record, ordinal) for record, ordinal in rows]

    def _agent_results(self, investigation_id: int) -> list[AgentResult]:
        rows = (
            self.db.query(AgentResultRow)
            .filter(
                AgentResultRow.investigation_id == investigation_id,
                AgentResultRow.org_id == self.org_id,
            )
            .order_by(AgentResultRow.ordinal)
            .all()
        )
        results: list[AgentResult] = []
        for row in rows:
            payload = dict(row.payload or {})
            findings = (
                self.db.query(FindingRow)
                .filter(
                    FindingRow.agent_result_id == row.id,
                    FindingRow.org_id == self.org_id,
                )
                .order_by(FindingRow.ordinal)
                .all()
            )
            results.append(
                AgentResult(
                    agent=row.agent,
                    version=row.version,
                    status=row.status,
                    confidence=row.confidence,
                    latency_ms=row.latency_ms,
                    error=row.error,
                    features=payload.get("features") or {},
                    provenance=payload.get("provenance") or [],
                    findings=[
                        Finding(
                            label=f.label,
                            value=f.value,
                            confidence=f.confidence,
                            source=f.source,
                            detail=f.detail,
                        )
                        for f in findings
                    ],
                )
            )
        return results


# -- module-level helpers, so the round trip is readable in one place --------


def _residual(state: InvestigationState) -> dict[str, Any]:
    """The contract fields no column and no table holds.

    `mode="json"` so enums and nested models are already JSON-safe values; the
    column is JSONB on PostgreSQL and a JSON-typed text column on SQLite, and
    neither will take a Python enum.
    """
    dumped = state.model_dump(mode="json")
    return {k: v for k, v in dumped.items() if k not in STORED_OUTSIDE_REST}


def _entity_pairs(entities: EntitySet) -> list[tuple[str, str, int]]:
    """Flatten an `EntitySet` into (kind, value, position) triples.

    `kind` is the contract's own field name. Values are stringified with
    `str()`, which for a float is the shortest representation that reads back to
    the same float — so an amount survives the round trip exactly rather than
    approximately.
    """
    out: list[tuple[str, str, int]] = []
    for kind in EntitySet.model_fields:
        values = getattr(entities, kind, None) or []
        for i, value in enumerate(values):
            out.append((kind, str(value), i))
    return out


def _to_entity_set(rows: list[tuple[EntityRecord, int]]) -> EntitySet:
    """Rebuild an `EntitySet` from its rows, restoring list order and type."""
    buckets: dict[str, list[tuple[int, Any]]] = {k: [] for k in EntitySet.model_fields}
    for record, ordinal in rows:
        if record.kind not in buckets:
            # A kind this contract version no longer has. Dropped rather than
            # raised on: an old row must not make an old case unreadable.
            continue
        caster = _ENTITY_TYPES.get(record.kind, str)
        buckets[record.kind].append((ordinal, caster(record.value)))
    return EntitySet(
        **{
            kind: [value for _, value in sorted(pairs, key=lambda p: p[0])]
            for kind, pairs in buckets.items()
        }
    )


def _to_evidence_item(row: EvidenceItemRow) -> dict[str, Any]:
    return {
        "id": row.item_id,
        "kind": row.kind,
        "filename": row.filename,
        "declared_type": row.declared_type,
        "media_type": row.media_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "uri": row.uri,
        "text": row.text,
        "received_at": row.received_at,
    }


def _summary(row: Investigation) -> dict[str, Any]:
    return {
        "case_id": row.case_id,
        "org_id": row.org_id,
        "status": row.status,
        "mode": row.mode,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
        "risk_score": row.risk_score,
        "risk_level": row.risk_level,
        "confidence": row.confidence,
        "classification": row.classification,
    }


__all__ = [
    "LINKABLE_ENTITY_FIELDS",
    "STORED_OUTSIDE_REST",
    "EvidenceStore",
    "OrgMismatch",
]
