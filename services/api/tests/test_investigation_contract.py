"""
The investigation contract — round-trip, bounds, and drift guards.

    .venv/bin/python -m pytest services/api/tests/test_investigation_contract.py -q

`InvestigationState` is the object every agent in Phases 1-4 reads and writes.
ARCHITECTURE.md calls a mistake here the most expensive one available, and it is
right: a field named wrong is renamed later across the orchestrator, every agent,
the persistence layer, the API and the UI at once.

So these tests pin the decisions, not just the syntax. Several exist purely to
stop a later change from quietly reversing a judgement made here:

  * an unscored investigation reads `None`, never `0` / `CALM`
  * `FraudCategory` has no UNKNOWN member
  * `EntitySet` field names match the knowledge graph's extractor exactly
  * every enum on the contract is covered by the drift check
  * `RecommendedAction` can express every line the engine already ships

The Pydantic -> JSON -> TypeScript direction is not tested here — it cannot be,
from Python. It is enforced by `npm run typecheck` against the generated
`investigation.fixture.ts`; see schema/mock_investigation.py.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

import pytest
from pydantic import ValidationError

from schema import check_contract, mock_investigation
from schema.models import (
    INVESTIGATION_CONTRACT_VERSION,
    AgentResult,
    AgentStatus,
    EntitySet,
    Event,
    FraudCategory,
    InvestigationState,
    InvestigationStatus,
    RecommendedAction,
    StateFrame,
    ThreatLevel,
    utc_now_iso,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def state() -> InvestigationState:
    return mock_investigation.build()


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------


def test_full_state_survives_a_json_round_trip(state: InvestigationState) -> None:
    """Every field, through JSON, back to Python, unchanged.

    The fixture populates every optional deliberately, so this covers the whole
    surface rather than the happy subset a hand-written state would touch.
    """
    encoded = state.model_dump_json()
    restored = InvestigationState.model_validate(json.loads(encoded))
    assert restored == state
    assert restored.model_dump(mode="json") == state.model_dump(mode="json")


def test_committed_json_fixture_is_current() -> None:
    """The committed artifact matches what the generator produces now.

    Same failure this project has already been bitten by twice: a metrics file
    that kept describing a model it no longer measured. A stale fixture would
    keep `npm run typecheck` green while checking a contract nobody uses.
    """
    on_disk = mock_investigation.JSON_OUT.read_text()
    assert on_disk == mock_investigation.to_json(mock_investigation.build())
    InvestigationState.model_validate(json.loads(on_disk))


def test_typescript_fixture_is_current_and_annotated() -> None:
    """The .ts fixture is what makes the typecheck a field-level contract check.

    If it stops being annotated with the type, tsc infers a structural type from
    the literal, every assertion silently passes, and the gate becomes theatre.
    """
    on_disk = mock_investigation.TS_OUT.read_text()
    assert on_disk == mock_investigation.to_typescript(mock_investigation.build())
    assert "const INVESTIGATION_FIXTURE: InvestigationState = {" in on_disk
    assert 'import type { InvestigationState } from "../types/contract";' in on_disk


def test_generator_is_deterministic() -> None:
    """No now(), no random ids — or the staleness check above cries wolf."""
    assert mock_investigation.to_json(mock_investigation.build()) == mock_investigation.to_json(
        mock_investigation.build()
    )


def test_minimal_state_is_valid_and_defaults_are_empty() -> None:
    s = InvestigationState(
        case_id="AGIS-1", org_id="aegis", created_by="u@aegis.local", created_at=utc_now_iso()
    )
    assert s.v == INVESTIGATION_CONTRACT_VERSION
    assert s.status is InvestigationStatus.QUEUED
    assert s.mode == "batch"
    assert (s.inputs, s.agent_results, s.degraded, s.trace, s.evidence) == ([], [], [], [], [])
    assert s.entities == EntitySet()
    assert s.transcript is None and s.graph_context is None


# --------------------------------------------------------------------------
# The live-call contract is untouched
# --------------------------------------------------------------------------


def test_existing_mock_stream_still_validates() -> None:
    """The inherited frame contract must not have moved.

    The investigation models were added to the same file; adding them must not
    change how a `StateFrame` validates, or every recorded fixture and the demo
    fallback stream break at once.
    """
    messages = json.loads((ROOT / "schema" / "mock-stream.json").read_text())
    states = [m for m in messages if m["type"] == "state"]
    events = [m for m in messages if m["type"] == "event"]
    assert states and events
    for m in states:
        StateFrame.model_validate(m)
    for m in events:
        Event.model_validate(m)


def test_a_bare_state_frame_still_validates() -> None:
    """A frame carrying only the required fields — the oldest mock shape."""
    frame = StateFrame(session_id="s-1", seq=0, t=0.0)
    assert frame.stage is None and frame.threat is None and frame.degraded == []


# --------------------------------------------------------------------------
# Bounds — a score outside its range is a bug, not a rendering quirk
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("risk_score", 100.1),
        ("risk_score", -1),
        ("confidence", 1.5),
        ("confidence", -0.1),
    ],
)
def test_out_of_range_scores_are_rejected(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        InvestigationState(
            case_id="AGIS-1",
            org_id="aegis",
            created_by="u@aegis.local",
            created_at=utc_now_iso(),
            **{field: value},
        )


def test_negative_latency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentResult(agent="a", version="0.1.0", status=AgentStatus.OK, latency_ms=-1)


def test_an_unknown_agent_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentResult(agent="a", version="0.1.0", status="fine")


# --------------------------------------------------------------------------
# Pinned design decisions
# --------------------------------------------------------------------------


def test_an_unscored_investigation_is_none_not_calm() -> None:
    """The decision worth defending hardest in this file.

    Defaulting `risk_score` to 0 would make every queued investigation render as
    CALM — a false negative wearing a number, on a screen a frightened person is
    reading. `None` forces the UI to say "not yet". `StateFrame.threat` is
    Optional for exactly the same reason.
    """
    s = InvestigationState(
        case_id="AGIS-1", org_id="aegis", created_by="u@aegis.local", created_at=utc_now_iso()
    )
    assert s.risk_score is None
    assert s.risk_level is None
    assert s.confidence is None
    assert s.classification is None
    assert s.risk_level is not ThreatLevel.CALM


def test_fraud_category_has_no_unknown_member() -> None:
    """`None` means "not classified"; BENIGN means "classified, and legitimate".

    An UNKNOWN member would collapse those, letting an unfinished investigation
    read as a cleared one.
    """
    assert "UNKNOWN" not in FraudCategory.__members__
    assert FraudCategory.BENIGN.value == "benign"
    # The twelve of DATASETS.md §3, plus the hard negative.
    assert len(FraudCategory) == 13


def test_entity_set_matches_the_graph_extractor() -> None:
    """`EntitySet` and `intel.entities.ExtractedEntities` must not drift apart.

    The knowledge graph keys its nodes off these names. A contract that said
    `accounts` where the extractor says `bank_accounts` would silently drop an
    entire entity class at the Phase 3 boundary — no error, just a fraud link
    that never gets drawn.
    """
    from services.api.intel.entities import ExtractedEntities

    extractor_fields = set(ExtractedEntities().as_dict())
    contract_fields = set(EntitySet.model_fields)
    missing = extractor_fields - contract_fields
    assert not missing, f"EntitySet is missing extractor fields: {sorted(missing)}"


def test_agent_status_values_match_the_architecture() -> None:
    """ARCHITECTURE.md §3 spells these lowercase; the UI switches on them."""
    assert [s.value for s in AgentStatus] == ["ok", "degraded", "skipped", "error"]


def test_skipped_is_distinct_from_ok() -> None:
    """Feature assembly in 4.1 must be able to tell "did not run" from "clean".

    Collapsing them is how a skipped APK scan becomes evidence of a safe APK.
    """
    assert AgentStatus.SKIPPED != AgentStatus.OK
    skipped = AgentResult(agent="apk_static", version="0.1.0", status=AgentStatus.SKIPPED)
    assert skipped.features == {} and skipped.confidence == 0.0


def test_timestamps_are_iso_utc_strings() -> None:
    """Strings, not datetimes — one representation that survives every round trip.

    Naive-vs-aware datetimes bit this project in 0.2 and again in 0.6. A value
    that is always ISO-8601 ending in `Z` cannot reproduce that.
    """
    now = utc_now_iso()
    assert now.endswith("Z") and "T" in now and "+" not in now
    from datetime import datetime, timezone

    parsed = datetime.fromisoformat(now.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc


# --------------------------------------------------------------------------
# The drift check covers the whole contract, not just the enums someone
# remembered to register
# --------------------------------------------------------------------------


def test_every_contract_enum_is_covered_by_the_drift_check() -> None:
    """A new enum with no entry in check_contract.PAIRS is unguarded.

    Without this, the failure is invisible: adding `class Foo(str, Enum)` to
    models.py and a matching array to types.ts passes every gate, and so does
    adding it to only one of them.
    """
    from schema import models

    registered = {cls for cls, _ in check_contract.PAIRS}
    declared = {
        obj
        for obj in vars(models).values()
        if isinstance(obj, type) and issubclass(obj, Enum) and obj.__module__ == models.__name__
    }
    unguarded = declared - registered
    assert not unguarded, (
        "enums on the contract with no drift check: "
        f"{sorted(c.__name__ for c in unguarded)} — add them to check_contract.PAIRS "
        "and export a matching `as const` array from types.ts"
    )


# --------------------------------------------------------------------------
# The contract has to be able to say what the system already says
# --------------------------------------------------------------------------

# Every line `engine/analyzer.py::_actions()` can produce, mapped to the member
# of `RecommendedAction` that expresses it. The mapping itself belongs to the
# adapter in task 1.7; what it is doing *here* is proving the vocabulary is
# complete before anything is built on it.
#
# This table caught the first draft of `RecommendedAction` being unable to
# express "Hang up" — advice the running system had been giving for months. A
# closed vocabulary that cannot say what the product says is not closed, it is
# incomplete, and the shortfall would have surfaced in 1.7 with a dozen call
# sites already written against it.
#
# The two route-level fallbacks in `routes/analyze.py` (an image with no
# readable text, audio with no speech) both ask the user for better evidence and
# map to PROVIDE_MORE_EVIDENCE.
SHIPPED_ACTION_VOCABULARY = {
    "Do not send money, share an OTP, or install anything they ask for.": (
        RecommendedAction.DO_NOT_PAY
    ),
    "Hang up. There is no legal consequence for ending a call.": (
        RecommendedAction.END_THE_CALL
    ),
    "Tell one other person now — isolation is what makes this work.": (
        RecommendedAction.SEEK_HELP_FROM_TRUSTED_PERSON
    ),
    "Report on 1930 or at cybercrime.gov.in.": RecommendedAction.REPORT_TO_CYBERCRIME,
    "Screenshot the payee name — it is evidence for the report.": (
        RecommendedAction.PRESERVE_EVIDENCE
    ),
    "Do not act on anything in this message yet.": RecommendedAction.DO_NOT_ACT_YET,
    "Look up the institution's number yourself and call them — never use a number the "
    "message supplies.": RecommendedAction.VERIFY_VIA_OFFICIAL_CHANNEL,
    "If money has already moved, report on 1930 immediately.": (
        RecommendedAction.REPORT_TO_CYBERCRIME
    ),
    "Paste the full message or more of the conversation for a real answer.": (
        RecommendedAction.PROVIDE_MORE_EVIDENCE
    ),
    "If a payment is involved, include the UPI ID or the amount requested.": (
        RecommendedAction.PROVIDE_MORE_EVIDENCE
    ),
    "Nothing detected — but verify any payment request in your own banking app.": (
        RecommendedAction.VERIFY_VIA_OFFICIAL_CHANNEL
    ),
    "Remember that no institution ever needs your OTP, PIN, or CVV.": (
        RecommendedAction.DO_NOT_SHARE_OTP
    ),
}


def test_every_shipped_action_line_has_a_contract_member() -> None:
    """Enumerate what the engine can actually say, and demand the enum covers it.

    If someone adds a line to `_actions()`, this fails until they say which
    member of the closed vocabulary it is — or add one deliberately. That is the
    intended friction: new safety advice should be a contract decision, not a
    string appended to a list.
    """
    from services.api.engine.analyzer import Finding, _actions

    payee_finding = Finding(label="Payee name mismatch", detail="", weight=0.0)
    produced: set[str] = set()
    for verdict in ("LIKELY_SCAM", "SUSPICIOUS", "INSUFFICIENT", "LIKELY_LEGITIMATE"):
        produced.update(_actions(verdict, []))
        produced.update(_actions(verdict, [payee_finding]))

    unmapped = produced - set(SHIPPED_ACTION_VOCABULARY)
    assert not unmapped, (
        "advice the engine gives that RecommendedAction cannot express: "
        f"{sorted(unmapped)} — map each to a member, or add one to "
        "schema/models.py and schema/types.ts in the same commit"
    )
    assert produced, "_actions() produced nothing — the vocabulary check is vacuous"


def test_the_action_vocabulary_table_is_not_stale() -> None:
    """Guard the guard: a mapping whose keys the engine no longer produces is
    dead weight that makes the check above look stronger than it is."""
    from services.api.engine.analyzer import Finding, _actions

    payee_finding = Finding(label="Payee name mismatch", detail="", weight=0.0)
    produced: set[str] = set()
    for verdict in ("LIKELY_SCAM", "SUSPICIOUS", "INSUFFICIENT", "LIKELY_LEGITIMATE"):
        produced.update(_actions(verdict, []))
        produced.update(_actions(verdict, [payee_finding]))

    stale = set(SHIPPED_ACTION_VOCABULARY) - produced
    assert not stale, f"mapped lines the engine no longer produces: {sorted(stale)}"
