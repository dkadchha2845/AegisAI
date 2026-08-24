"""
The evidence store — task 1.5's four acceptance criteria, and the invariants
that keep them true after the next change.

The criteria, and where each is checked:

| Criterion | Test |
|---|---|
| Every agent result persisted and re-readable | `test_agent_results_are_re_readable_on_their_own` |
| A full state rebuilds from the DB | `test_a_fully_populated_state_round_trips` |
| A cross-org read is impossible | `test_*_cannot_see_another_org*` (six of them) |
| Migrations run forward and back | `test_migrations.py` |

Every test runs against its own temp-file SQLite database rather than the
process-wide ephemeral one. Two reasons: the entity table is deduplicated per
organisation and shared state between tests would make an assertion about "the
cases this identifier appears in" depend on execution order, and a store test
that cannot be run in isolation is a store test that will eventually be
debugged by deleting it.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from schema.models import (
    AgentResult,
    AgentStatus,
    EntitySet,
    EvidenceFinding,
    EvidenceItem,
    ExtractedText,
    Finding,
    FraudCategory,
    GraphContext,
    GraphNeighbour,
    InputType,
    InvestigationState,
    InvestigationStatus,
    Recommendation,
    RecommendedAction,
    RetrievedChunk,
    Severity,
    Stage,
    ThreatLevel,
    TIRecord,
    TraceSpan,
    Transcript,
    Utterance,
    VictimState,
    utc_now_iso,
)
from services.api.db import Base
from services.api.stores import models as store_models
from services.api.stores.evidence import (
    LINKABLE_ENTITY_FIELDS,
    STORED_OUTSIDE_REST,
    EvidenceStore,
    OrgMismatch,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture
def session(tmp_path):
    """A private SQLite database with the full schema, torn down with the test."""
    from services.api import models_db  # noqa: F401  (register the platform tables)

    engine = create_engine(f"sqlite:///{tmp_path / 'store.db'}")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _state(case_id: str = "AEG-0001", org_id: str = "org-alpha", **over) -> InvestigationState:
    """A minimal but realistic investigation. Overridable field by field."""
    base = dict(
        case_id=case_id,
        org_id=org_id,
        created_by="analyst@aegis.local",
        created_at="2026-08-25T09:00:00Z",
        status=InvestigationStatus.COMPLETE,
        inputs=[EvidenceItem(id="ev-1", kind=InputType.TEXT, text="aapka parcel customs mein hai")],
        input_types=[InputType.TEXT],
        entities=EntitySet(phones=["+919812345678"], upi_ids=["refund@okaxis"]),
        agent_results=[
            AgentResult(
                agent="text_agent",
                version="1.0.0",
                status=AgentStatus.OK,
                confidence=0.82,
                latency_ms=41,
                findings=[Finding(label="fear_pressure", value="high", source="muril:v3")],
            )
        ],
        risk_score=88.0,
        risk_level=ThreatLevel.CRITICAL,
    )
    base.update(over)
    return InvestigationState(**base)


def _fully_populated(case_id: str = "AEG-FULL", org_id: str = "org-alpha") -> InvestigationState:
    """A state with *every* contract field set to a non-default value.

    Deliberately exhaustive. A round-trip test on a half-filled object proves
    only that the fields someone remembered survive, and the field that gets
    dropped is always the one nobody put in the fixture.
    """
    return InvestigationState(
        case_id=case_id,
        org_id=org_id,
        created_by="analyst@aegis.local",
        created_at="2026-08-25T09:00:00Z",
        completed_at="2026-08-25T09:00:12Z",
        mode="realtime",
        status=InvestigationStatus.COMPLETE,
        inputs=[
            EvidenceItem(
                id="ev-1",
                kind=InputType.SCREENSHOT,
                filename="notice.jpg",
                declared_type="image/jpeg",
                media_type="image/png",
                size_bytes=48123,
                sha256="a" * 64,
                uri="s3://evidence/org-alpha/ev-1",
                text=None,
                received_at="2026-08-25T08:59:58Z",
            ),
            EvidenceItem(id="ev-2", kind=InputType.URL, text="http://sbi-kyc-verify.example/login"),
        ],
        input_types=[InputType.SCREENSHOT, InputType.URL],
        extracted_text=[
            ExtractedText(
                source_ref="ev-1",
                text="Your parcel is held by customs",
                language="en",
                confidence=0.62,
                extractor="ocr:tesseract",
            )
        ],
        entities=EntitySet(
            phones=["+919812345678", "+911140001234"],
            upi_ids=["refund@okaxis"],
            emails=["cbi.notice@example.org"],
            wallets=["0xdeadbeef"],
            bank_accounts=["50100123456789"],
            domains=["sbi-kyc-verify.example"],
            urls=["http://sbi-kyc-verify.example/login"],
            ips=["203.0.113.9"],
            apps=["com.fake.rat"],
            orgs=["Central Bureau of Investigation"],
            amounts=[2500.5, 19999.0],
            authorities=["CBI"],
            banks=["SBI"],
            locations=["Mumbai"],
            scam_keywords=["digital arrest"],
        ),
        transcript=Transcript(
            final=[
                Utterance(
                    id="u1",
                    speaker="CALLER",
                    text="main CBI se bol raha hoon",
                    t0=0.0,
                    t1=2.4,
                    stage=Stage.FEAR_INDUCTION,
                    confidence=0.91,
                    victim_state=VictimState.PANICKED,
                )
            ],
            partial="aapko arrest",
            partial_speaker="CALLER",
        ),
        agent_results=[
            AgentResult(
                agent="url_agent",
                version="1.2.0",
                status=AgentStatus.DEGRADED,
                confidence=0.55,
                latency_ms=1204,
                features={"domain_age_days": 3.0, "has_login_form": 1.0},
                provenance=["whois", "urlhaus:cached"],
                error="urlhaus unreachable; served from snapshot",
                findings=[
                    Finding(
                        label="domain_age_days",
                        value="3",
                        confidence=0.99,
                        source="whois",
                        detail="registered three days ago",
                    ),
                    Finding(label="has_login_form", value="true", source="fetch"),
                ],
            ),
            AgentResult(
                agent="apk_agent",
                version="0.9.0",
                status=AgentStatus.SKIPPED,
                confidence=0.0,
                latency_ms=0,
            ),
        ],
        threat_intel=[
            TIRecord(
                indicator="sbi-kyc-verify.example",
                indicator_type="domain",
                source="urlhaus",
                malicious=None,
                confidence=0.0,
                observed_at="2026-08-20T00:00:00Z",
                retrieved_at="2026-08-25T09:00:03Z",
                reference="https://urlhaus.abuse.ch/host/sbi-kyc-verify.example/",
                cached=True,
            )
        ],
        graph_context=GraphContext(
            prior_observations=4,
            prior_case_ids=["AEG-0002"],
            neighbours=[
                GraphNeighbour(
                    key="upi:refund@okaxis",
                    kind="upi",
                    value="refund@okaxis",
                    relation="SHARED_UPI",
                    shared_cases=3,
                )
            ],
            cluster_id="cl-17",
            cluster_risk=77.5,
            centrality=0.31,
            first_seen="2026-06-01T00:00:00Z",
            last_seen="2026-08-24T00:00:00Z",
            backend="neo4j",
        ),
        rag_context=[
            RetrievedChunk(
                chunk_id="rbi-2024-07#3",
                text="Banks never ask for OTP.",
                source="RBI circular 2024-07",
                citation="RBI/2024-25/07 §3",
                score=0.82,
                retriever="hybrid",
            )
        ],
        risk_features={"domain_age_days": 3.0, "fear_pressure": 0.91},
        risk_score=91.5,
        risk_level=ThreatLevel.CRITICAL,
        confidence=0.87,
        classification=FraudCategory.DIGITAL_ARREST,
        evidence=[
            EvidenceFinding(
                id="f-1",
                title="Domain registered three days ago",
                detail="A bank does not move its login page to a new domain.",
                severity=Severity.HIGH,
                confidence=0.9,
                contribution=None,
                agent="url_agent",
                sources=["whois"],
            )
        ],
        recommendations=[
            Recommendation(
                action=RecommendedAction.DO_NOT_SHARE_OTP,
                detail="No bank or police officer will ever ask for it.",
                urgency=Severity.CRITICAL,
                sources=["RBI/2024-25/07 §3"],
            )
        ],
        degraded=["agent:url_agent:degraded", "ti:urlhaus:cached"],
        trace=[
            TraceSpan(
                span_id="investigate/url_agent#1@1",
                node="investigate/url_agent",
                agent="url_agent",
                version="1.2.0",
                t_start=0.01,
                t_end=1.22,
                latency_ms=1204,
                status=AgentStatus.DEGRADED,
                attempt=1,
                depth=0,
                parent_span_id=None,
                error="urlhaus unreachable; served from snapshot",
            )
        ],
    )


# --- the round trip ---------------------------------------------------------


def test_a_fully_populated_state_round_trips(session):
    """The headline criterion: a full state rebuilds from the database.

    Equality on the whole model, not a field-by-field spot check — the point is
    that *nothing* was lost, and enumerating what to compare would re-introduce
    exactly the blind spot the exhaustive fixture exists to remove.
    """
    original = _fully_populated()
    store = EvidenceStore(session, "org-alpha")
    store.save(original)

    assert store.load("AEG-FULL") == original


def test_amounts_survive_as_floats_not_strings(session):
    """Entities are stored as text; an amount must still come back a float.

    `EntitySet.amounts` is the one numeric entity list, and a store that
    returned "2500.5" would break the moment anything summed it.
    """
    store = EvidenceStore(session, "org-alpha")
    store.save(_state(entities=EntitySet(amounts=[2500.5, 0.1, 19999.0])))
    amounts = store.load("AEG-0001").entities.amounts
    assert amounts == [2500.5, 0.1, 19999.0]
    assert all(isinstance(a, float) for a in amounts)


def test_entity_list_order_is_preserved(session):
    """Rebuilt lists keep the extractor's order, not the database's.

    The extractors are deterministic (1.3 spent a module on it). If the store
    reordered on the way out, two runs of the same input would produce states
    that differ, and the fingerprint that guards determinism would be comparing
    the wrong thing.
    """
    phones = ["+919000000003", "+919000000001", "+919000000002"]
    store = EvidenceStore(session, "org-alpha")
    store.save(_state(entities=EntitySet(phones=phones)))
    assert store.load("AEG-0001").entities.phones == phones


def test_saving_twice_replaces_children_rather_than_appending(session):
    """Re-running an investigation must not double its agent results."""
    store = EvidenceStore(session, "org-alpha")
    store.save(_fully_populated())
    store.save(_fully_populated())

    reloaded = store.load("AEG-FULL")
    assert len(reloaded.agent_results) == 2
    assert len(reloaded.inputs) == 2
    assert store.count() == 1
    assert session.query(store_models.FindingRow).count() == 2


def test_duplicate_entity_values_do_not_lose_the_investigation(session):
    """`EntitySet` is documented as deduplicated; a duplicate must still save.

    The join's primary key is (investigation, entity), so a repeated value would
    otherwise collide and take the whole save down with it. Losing a case to a
    phone number listed twice is not a trade worth making for strictness.
    """
    store = EvidenceStore(session, "org-alpha")
    store.save(_state(entities=EntitySet(phones=["+919812345678", "+919812345678"])))
    assert store.load("AEG-0001").entities.phones == ["+919812345678"]


# --- agent results and findings, addressable on their own -------------------


def test_agent_results_are_re_readable_on_their_own(session):
    """Every agent result persisted and re-readable — without the whole state."""
    original = _fully_populated()
    store = EvidenceStore(session, "org-alpha")
    store.save(original)

    results = store.agent_results("AEG-FULL")
    assert [r.agent for r in results] == ["url_agent", "apk_agent"]
    assert results == original.agent_results

    degraded = results[0]
    assert degraded.status is AgentStatus.DEGRADED
    assert degraded.features == {"domain_age_days": 3.0, "has_login_form": 1.0}
    assert degraded.provenance == ["whois", "urlhaus:cached"]
    assert degraded.error


def test_findings_are_queryable_by_label_across_cases(session):
    """The query `findings` has its own table for."""
    store = EvidenceStore(session, "org-alpha")
    store.save(_fully_populated("AEG-A"))
    store.save(_fully_populated("AEG-B"))

    hits = store.findings(label="domain_age_days")
    assert len(hits) == 2
    assert {f.value for f in hits} == {"3"}
    assert store.findings(case_id="AEG-A", label="domain_age_days") == [hits[0]]
    assert store.findings(label="no_such_label") == []


def test_cases_for_entity_finds_the_shared_identifier(session):
    """What `GraphContext.prior_case_ids` will be built from in Phase 3."""
    store = EvidenceStore(session, "org-alpha")
    store.save(_state("AEG-A", entities=EntitySet(upi_ids=["refund@okaxis"])))
    store.save(_state("AEG-B", entities=EntitySet(upi_ids=["refund@okaxis"])))
    store.save(_state("AEG-C", entities=EntitySet(upi_ids=["other@okhdfc"])))

    assert store.cases_for_entity("upi_ids", "refund@okaxis") == ["AEG-A", "AEG-B"]
    assert store.cases_for_entity("upi_ids", "nobody@okaxis") == []


def test_list_cases_returns_summaries_newest_first(session):
    store = EvidenceStore(session, "org-alpha")
    store.save(_state("AEG-OLD", created_at="2026-08-01T00:00:00Z"))
    store.save(_state("AEG-NEW", created_at="2026-08-24T00:00:00Z"))

    listed = store.list_cases()
    assert [c["case_id"] for c in listed] == ["AEG-NEW", "AEG-OLD"]
    assert listed[0]["risk_level"] == "CRITICAL"
    assert store.list_cases(status="QUEUED") == []


# --- tenant isolation -------------------------------------------------------


def _two_orgs(session):
    alpha, beta = EvidenceStore(session, "org-alpha"), EvidenceStore(session, "org-beta")
    alpha.save(_fully_populated("SHARED-ID", "org-alpha"))
    beta.save(_state("SHARED-ID", "org-beta", entities=EntitySet(upi_ids=["refund@okaxis"])))
    return alpha, beta


def test_the_same_case_id_in_two_orgs_is_two_cases(session):
    """Uniqueness is per organisation. A global constraint would let one tenant's
    write fail because of a case it is not allowed to know exists."""
    alpha, beta = _two_orgs(session)
    assert alpha.load("SHARED-ID").created_by == "analyst@aegis.local"
    assert alpha.load("SHARED-ID").risk_score == 91.5
    assert beta.load("SHARED-ID").risk_score == 88.0
    assert alpha.count() == 1 and beta.count() == 1


def test_a_store_cannot_load_another_orgs_case(session):
    _two_orgs(session)
    gamma = EvidenceStore(session, "org-gamma")
    assert gamma.load("SHARED-ID") is None
    assert gamma.exists("SHARED-ID") is False
    assert gamma.count() == 0
    assert gamma.list_cases() == []


def test_a_store_cannot_read_another_orgs_agent_results_or_findings(session):
    _two_orgs(session)
    gamma = EvidenceStore(session, "org-gamma")
    assert gamma.agent_results("SHARED-ID") == []
    assert gamma.findings() == []
    assert gamma.findings(label="domain_age_days") == []
    # Naming the case explicitly must not become a way around the scope: the
    # case id resolves through the same org-scoped lookup as everything else.
    assert gamma.findings(case_id="SHARED-ID") == []
    assert gamma.findings(case_id="SHARED-ID", label="domain_age_days") == []


def test_a_store_cannot_see_another_orgs_entities(session):
    """The same UPI ID in two tenants is two rows, and neither reaches the other.

    Cross-tenant linkage is Module 2's graph, deliberately a different store
    with a different policy — see `models.EntityRecord`.
    """
    alpha, beta = _two_orgs(session)
    assert alpha.cases_for_entity("upi_ids", "refund@okaxis") == ["SHARED-ID"]
    assert beta.cases_for_entity("upi_ids", "refund@okaxis") == ["SHARED-ID"]
    assert EvidenceStore(session, "org-gamma").cases_for_entity("upi_ids", "refund@okaxis") == []
    # Two rows, one per tenant, rather than one shared row.
    assert session.query(store_models.EntityRecord).filter_by(kind="upi_ids").count() == 2


def test_a_store_cannot_delete_another_orgs_case(session):
    alpha, beta = _two_orgs(session)
    assert EvidenceStore(session, "org-gamma").delete_case("SHARED-ID") is False
    assert alpha.exists("SHARED-ID") and beta.exists("SHARED-ID")


def test_a_store_refuses_to_write_another_orgs_state(session):
    """Writing is scoped too. A route holding a state it was never granted must
    not be able to launder it into the store by picking the wrong repository."""
    alpha = EvidenceStore(session, "org-alpha")
    with pytest.raises(OrgMismatch):
        alpha.save(_state("AEG-X", org_id="org-beta"))
    assert alpha.exists("AEG-X") is False


def test_a_store_without_an_org_is_refused_at_construction(session):
    """An empty scope filters to nothing, which reads exactly like an empty
    tenant. Failing here means the dropped org surfaces where it was dropped."""
    for bad in ("", "   "):
        with pytest.raises(ValueError):
            EvidenceStore(session, bad)


def test_every_table_in_this_store_carries_a_non_nullable_org_id():
    """The isolation rule, checked structurally rather than trusted.

    One rule with no exceptions is what makes the claim checkable in a line. A
    seventh table added without `org_id` fails here rather than quietly becoming
    the one place a tenant boundary does not exist.
    """
    for table in store_models.EVIDENCE_TABLES:
        column = table.__table__.columns.get("org_id")
        assert column is not None, f"{table.__tablename__} has no org_id"
        assert not column.nullable, f"{table.__tablename__}.org_id is nullable"


def test_only_the_repository_queries_these_tables():
    """`stores/models.py` is imported by the repository, the schema plumbing and
    the tests — nothing else.

    The isolation is the repository, not the database: there is no row-level
    security underneath it. A second module building its own query against these
    tables would bypass every scoping rule above while still looking correct, so
    the boundary is asserted rather than assumed.
    """
    allowed = {
        "services/api/stores/evidence.py",
        "services/api/db.py",
        "services/api/migrations/env.py",
    }
    pattern = re.compile(r"stores(\.models| import models)|stores\.models")
    offenders = []
    for path in (REPO_ROOT / "services").rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in allowed or "/tests/" in rel or "__pycache__" in rel:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], f"these modules bypass EvidenceStore: {offenders}"


# --- erasure ----------------------------------------------------------------


def test_delete_removes_every_child_row(session):
    """Erasure is explicit, not a cascade — SQLite would not enforce one.

    Counted directly against the tables rather than through `load()`, because
    "the repository can no longer find it" and "the rows are gone" are different
    claims, and a citizen exercising a right to erasure is owed the second.
    """
    store = EvidenceStore(session, "org-alpha")
    store.save(_fully_populated())
    assert store.delete_case("AEG-FULL") is True

    for table in store_models.EVIDENCE_TABLES:
        assert session.query(table).count() == 0, table.__tablename__


def test_delete_keeps_entities_another_case_still_needs(session):
    """Orphans go; shared identifiers stay. Deleting one case must not blind the
    store to an identifier a surviving case is built on."""
    store = EvidenceStore(session, "org-alpha")
    store.save(_state("AEG-A", entities=EntitySet(upi_ids=["shared@okaxis"], phones=["+9111"])))
    store.save(_state("AEG-B", entities=EntitySet(upi_ids=["shared@okaxis"])))

    store.delete_case("AEG-A")

    assert store.cases_for_entity("upi_ids", "shared@okaxis") == ["AEG-B"]
    assert store.cases_for_entity("phones", "+9111") == []
    kinds = {e.kind for e in session.query(store_models.EntityRecord).all()}
    assert kinds == {"upi_ids"}


def test_deleting_an_absent_case_is_false_not_an_error(session):
    assert EvidenceStore(session, "org-alpha").delete_case("nope") is False


# --- the storage partition --------------------------------------------------


def test_nothing_is_stored_in_two_places(session):
    """`rest` holds what no column and no table holds, and nothing else.

    Two copies of a field is two answers to the same question, and the one that
    gets read is whichever the next author reached for first.
    """
    store = EvidenceStore(session, "org-alpha")
    store.save(_fully_populated())
    row = session.query(store_models.Investigation).one()

    assert set(row.rest) & STORED_OUTSIDE_REST == set()
    assert "agent_results" not in row.rest
    assert "entities" not in row.rest
    assert "inputs" not in row.rest


def test_residual_covers_every_contract_field(session):
    """Every `InvestigationState` field is stored somewhere, exactly once.

    This fails when a field is added to the contract — deliberately. Nothing
    breaks at runtime if it happens (an unrecognised field lands in `rest` and
    round trips fine), but a new field that ought to be a queryable column
    should be a decision someone makes, not a default someone inherits. If
    `rest` is the right home, add the name to the expected set below.
    """
    expected_rest = {
        "type",
        "input_types",
        "extracted_text",
        "transcript",
        "threat_intel",
        "graph_context",
        "rag_context",
        "risk_features",
        "evidence",
        "recommendations",
        "degraded",
        "trace",
    }
    contract_fields = set(InvestigationState.model_fields)
    assert STORED_OUTSIDE_REST | expected_rest == contract_fields, (
        "InvestigationState changed. Decide where the new field lives: a column "
        "on `investigations`, a table of its own, or `rest`."
    )

    store = EvidenceStore(session, "org-alpha")
    store.save(_fully_populated())
    assert set(session.query(store_models.Investigation).one().rest) == expected_rest


def test_linkable_matches_the_ten_fields_the_contract_names(session):
    """`linkable` is a safety property: it is what stops Phase 3 building a fraud
    edge out of two cases both mentioning "SBI".

    The contract's `EntitySet` docstring names ten linkable fields and says the
    display-context ones must never become graph edges. Anything else is stored
    unlinkable, because ten is what the contract warrants.
    """
    assert set(EntitySet.model_fields) >= LINKABLE_ENTITY_FIELDS
    for never in ("banks", "locations", "scam_keywords", "amounts", "authorities"):
        assert never not in LINKABLE_ENTITY_FIELDS

    store = EvidenceStore(session, "org-alpha")
    store.save(_fully_populated())
    by_kind = {e.kind: e.linkable for e in session.query(store_models.EntityRecord).all()}
    assert by_kind, "the fully populated fixture should write every entity kind"
    for kind, linkable in by_kind.items():
        assert linkable is (kind in LINKABLE_ENTITY_FIELDS), kind


def test_an_entity_kind_the_contract_no_longer_has_is_skipped_not_fatal(session):
    """A row written by a different contract version must not make a case
    unreadable.

    `EntitySet` will gain and lose fields. When it loses one, the rows are still
    in the database, and the choice is between dropping them on read and
    refusing to open the case. An evidence store that cannot open an old case
    because the schema moved on is the failure this branch exists to avoid.
    """
    store = EvidenceStore(session, "org-alpha")
    store.save(_state(entities=EntitySet(phones=["+919812345678"])))
    row = session.query(store_models.EntityRecord).one()
    row.kind = "telepathy"  # a field this contract version does not have
    session.commit()

    reloaded = store.load("AEG-0001")
    assert reloaded is not None
    assert reloaded.entities.phones == []


def test_entity_values_are_stored_exactly_as_extracted(session):
    """No canonicalisation. Deciding two identifiers are the same identifier is
    the graph's job; an evidence store that rewrites evidence is not one."""
    store = EvidenceStore(session, "org-alpha")
    store.save(_state(entities=EntitySet(domains=["SBI-Kyc-Verify.Example"])))
    assert store.load("AEG-0001").entities.domains == ["SBI-Kyc-Verify.Example"]


def test_an_unscored_investigation_does_not_come_back_as_calm(session):
    """`risk_score` stays None. Zero would be a false negative wearing a number,
    and the contract makes the field Optional for exactly this reason."""
    store = EvidenceStore(session, "org-alpha")
    store.save(
        _state(
            "AEG-QUEUED",
            status=InvestigationStatus.QUEUED,
            risk_score=None,
            risk_level=None,
            agent_results=[],
        )
    )
    reloaded = store.load("AEG-QUEUED")
    assert reloaded.risk_score is None
    assert reloaded.risk_level is None
    assert reloaded.status is InvestigationStatus.QUEUED


def test_an_empty_investigation_round_trips(session):
    """The benign case: nothing submitted, nothing found, nothing broken."""
    empty = InvestigationState(
        case_id="AEG-EMPTY",
        org_id="org-alpha",
        created_by="",
        created_at=utc_now_iso(),
    )
    store = EvidenceStore(session, "org-alpha")
    store.save(empty)
    assert store.load("AEG-EMPTY") == empty


def test_the_schema_has_the_six_tables_the_task_names(session):
    """1.5 names six tables. This is the list, checked against the database."""
    names = set(inspect(session.get_bind()).get_table_names())
    assert {
        "investigations",
        "evidence_items",
        "agent_results",
        "findings",
        "entities",
        "case_entities",
    } <= names
