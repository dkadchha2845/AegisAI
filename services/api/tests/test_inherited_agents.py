"""
The inherited engine, as agents — task 1.7's three acceptance criteria.

    .venv/bin/python -m pytest services/api/tests/test_inherited_agents.py -q

| Criterion | Where |
|---|---|
| The existing tests still pass unmodified | the rest of this suite, and `git diff` on `services/api/engine/` |
| Each adapter emits a valid `AgentResult` | `test_every_adapter_returns_a_valid_agent_result` |
| The live-call flow works through the new orchestrator **and** the old path | `test_the_live_session_and_the_graph_agree_*` |

The first criterion is the one that shapes this file. "Adapt without rewriting"
is only checkable if something proves nothing was quietly reimplemented on the
way, and a passing test suite does not prove that — an adapter that recomputed
the coercion index with slightly different constants would pass every test that
exists. So the bar here is **equality with the old path**: for the same input,
the graph must produce the same stage labels, the same manipulation map, the
same coercion index, the same trust percentage, the same script similarity and
the same fused drivers as `engine/analyzer.analyze_text`. A difference anywhere
is a rewrite that happened by accident.

One number deliberately does *not* match, and the tests say why rather than
working around it: on evidence carrying a dispositive finding, `analyze_text`
floors the score above the fused value. That floor is a deterministic rule
(ARCHITECTURE.md §4 puts it inside the fusion box task 4.6 builds), and the
findings it acts on for the sample below come from `engine/upi.py`, which is
task 2.6's Financial Fraud Agent and not one of the seven modules 1.7 wraps.
`test_the_gap_to_the_old_paths_final_score_is_attributable` pins exactly that,
so the day either lands the difference has to be re-explained rather than
silently absorbed.
"""

from __future__ import annotations

import asyncio
import pathlib
import re
from typing import Any, Dict, List

import pytest

from schema.models import (
    AgentResult,
    AgentStatus,
    EvidenceItem,
    InputType,
    InvestigationState,
    utc_now_iso,
)
from services.api.agents import registry
from services.api.agents.base import STAGE_ORDER, AgentContext, stage_of
from services.api.agents.inherited import conversation, signals
from services.api.engine.analyzer import analyze_text, normalise
from services.api.engine.classifier import MIN_STAGE_CONFIDENCE, stage_rank, threat_weight
from services.api.engine.spoofing import analyze_number
from services.api.engine.threat import SCRIPT_MIN, ManipulationAccumulator, fuse
from services.api.orchestration import graph as orch
from services.api.orchestration.policy import POLICIES

# A digital-arrest call with both sides, so every adapter has something to do.
CALL = """CALLER: Main CBI crime branch se Inspector Sharma bol raha hoon, badge number 4471.
VICTIM: ji sir kya hua
CALLER: Aapke naam par ek parcel mila hai jisme drugs the, money laundering ka non-bailable case register ho gaya hai.
VICTIM: nahi sir maine kuch nahi kiya, main bank jaunga check karne
CALLER: Ye matter puri tarah confidential hai, kisi ko mat bataiye aur call disconnect mat kijiye, aap digital arrest par hain.
VICTIM: please sir dar lag raha hai kya karu
CALLER: Verification ke liye jo OTP aaya hai wo bataiye aur RBI ke supervised account mein security deposit transfer kar dijiye."""

SCAM_SMS = (
    "URGENT: your SBI KYC is suspended. Pay Rs 4999 to refund@okaxis within 2 hours "
    "or your account will be blocked. Verify at http://sbi-kyc-verify.top"
)

BENIGN = {
    "sbi debit alert": (
        "Dear Customer, Rs 450.00 debited from A/c XX3421 on 24-08-26 to VPA "
        "grocerystore@ybl. Not you? Call 1800-11-2211. -SBI"
    ),
    "delivery notice": (
        "Your Amazon order 402-8891 is out for delivery today between 2pm and 6pm. "
        "Track it in the app."
    ),
    "bank otp reminder": (
        "This is a reminder from HDFC Bank: we will never ask for your OTP, PIN or "
        "CVV. Please do not share them with anyone."
    ),
}

INHERITED = (
    signals.STAGE_CLASSIFIER,
    signals.COERCION_TRACKER,
    signals.TRUST_PASSPORT,
    signals.SCRIPT_MATCH,
    signals.NUMBER_SPOOFING,
    signals.DIGITAL_TWIN,
    signals.THREAT_FUSION,
)


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------


def make_state(text: str, **kw: Any) -> InvestigationState:
    return InvestigationState(
        case_id="AEG-INHERITED",
        org_id="org-1",
        created_by="test@aegis.local",
        created_at=utc_now_iso(),
        inputs=[EvidenceItem(id="ev-01", kind=InputType.TEXT, text=text)],
        input_types=[InputType.TEXT],
        **kw,
    )


def investigate(state: InvestigationState) -> InvestigationState:
    return asyncio.run(orch.investigate(state))


def by_agent(state: InvestigationState) -> Dict[str, AgentResult]:
    return {r.agent: r for r in state.agent_results}


def run_one(agent_name: str, state: InvestigationState) -> AgentResult:
    """One adapter, directly, with no graph around it."""
    agent = registry.get(agent_name)
    ctx = AgentContext(org_id=state.org_id, case_id=state.case_id)
    return asyncio.run(agent.run(state, ctx))


def values(result: AgentResult, label: str) -> List[str]:
    return [f.value or "" for f in result.findings if f.label == label]


# --------------------------------------------------------------------------
# Criterion 2 — each adapter emits a valid AgentResult
# --------------------------------------------------------------------------


def test_every_adapter_is_registered_with_a_pinned_version() -> None:
    for name in INHERITED:
        agent = registry.get(name)
        assert agent.name == name
        assert re.fullmatch(r"\d+\.\d+\.\d+", agent.version), agent.version


def test_every_adapter_returns_a_valid_agent_result() -> None:
    """The uniform shape is the whole reason the orchestrator can fan out."""
    done = investigate(make_state(CALL))
    produced = by_agent(done)

    for name in INHERITED:
        if name == signals.NUMBER_SPOOFING:
            continue  # no number in this evidence; covered by its own tests
        result = produced.get(name)
        assert result is not None, f"{name} produced no result"
        assert isinstance(result, AgentResult)
        assert result.agent == name
        assert 0.0 <= result.confidence <= 1.0
        assert result.status in (AgentStatus.OK, AgentStatus.DEGRADED)
        assert result.provenance, f"{name} named no source"
        assert all(0.0 <= f.confidence <= 1.0 for f in result.findings)


def test_the_adapters_sit_in_the_tiers_they_declare() -> None:
    """Tier membership is what gives the graph its shape, and the ordering here
    is load-bearing: the two JUDGE agents read what the REASON tier published,
    so a tier declared wrong would make them fuse over nothing."""
    tiers = {name: stage_of(registry.get(name)).value for name in INHERITED}
    assert tiers == {
        signals.STAGE_CLASSIFIER: "reason",
        signals.COERCION_TRACKER: "reason",
        signals.TRUST_PASSPORT: "reason",
        signals.SCRIPT_MATCH: "reason",
        signals.NUMBER_SPOOFING: "investigate",
        signals.DIGITAL_TWIN: "judge",
        signals.THREAT_FUSION: "judge",
    }
    order = [s.value for s in STAGE_ORDER]
    assert order.index("investigate") < order.index("reason") < order.index("judge")


def test_the_stage_classifier_gets_the_budget_reserved_for_it() -> None:
    """`policy.py` recorded this budget before the agent existed, under a
    placeholder name. A key that matches no agent is a silent no-op — which is
    the exact defect 1.3's end-to-end run caught — so the reservation was
    renamed to the agent rather than the agent to the reservation."""
    policy = POLICIES[signals.STAGE_CLASSIFIER]
    assert policy.timeout_s == 8.0
    assert policy.attempts == 1, "a model that is broken is not fixed by a retry"


def test_no_adapter_reaches_into_a_private_name_in_the_engine() -> None:
    """"Internals untouched" cuts both ways.

    Not editing the engine is half of it; the other half is not depending on
    anything it did not choose to expose, because a private name that an adapter
    reads is a name the engine can no longer change. `analyze_text` itself does
    this in one place (`coercion._victim_state`), which is exactly the coupling
    this package is not allowed to copy.
    """
    package = pathlib.Path(__file__).resolve().parents[1] / "agents" / "inherited"
    private = re.compile(r"(?:engine\.\w+|from\s+\.\.\.engine[.\w]*)\s+import\s+[^\n]*\b_\w+")
    attribute = re.compile(r"\b(?:classifier|coercion|passport|scripts|spoofing|threat|twin)_?\w*\._\w+")
    offenders = []
    for path in sorted(package.glob("*.py")):
        source = "\n".join(
            line for line in path.read_text().splitlines() if not line.strip().startswith("#")
        )
        if private.search(source) or attribute.search(source):
            offenders.append(path.name)
    assert offenders == [], f"adapters reaching into engine internals: {offenders}"


# --------------------------------------------------------------------------
# Criterion 1 — the same conversation, the same numbers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        CALL,
        SCAM_SMS,
        BENIGN["sbi debit alert"],
        '[{"speaker": "CALLER", "text": "main CBI se bol raha hoon"}, '
        '{"speaker": "VICTIM", "text": "ji sir"}]',
    ],
    ids=["labelled-call", "one-sided-sms", "benign-sms", "json-transcript"],
)
def test_the_graph_sees_exactly_the_conversation_the_analyzer_sees(raw: str) -> None:
    """Both paths parse through `analyzer.normalise`, so this is one
    implementation reached two ways rather than two that agree today."""
    turns = conversation.turns(make_state(raw))
    assert [(t.speaker, t.text) for t in turns] == normalise(raw)


def test_the_conversation_comes_from_the_most_processed_source_available() -> None:
    """Transcript, then extracted text, then the raw items — first non-empty wins.

    Not concatenated, and that is the decision worth pinning: `extracted_text` is
    *derived from* the inputs, so reading both would score the same words twice
    and inflate every cumulative signal in the engine — the manipulation
    accumulator, the passport's latched checks, the coercion history.
    """
    from schema.models import ExtractedText, Stage, Transcript, Utterance

    inline = make_state("pasted body")
    assert conversation.source_text(inline) == "pasted body"

    ocr = inline.model_copy(
        update={
            "extracted_text": [
                ExtractedText(source_ref="ev-01", text="read off the screenshot", extractor="ocr:tesseract")
            ]
        }
    )
    assert conversation.source_text(ocr) == "read off the screenshot"

    spoken = ocr.model_copy(
        update={
            "transcript": Transcript(
                final=[
                    Utterance(
                        id="u1", speaker="CALLER", text="main CBI se bol raha hoon",
                        t0=0.0, t1=2.0, stage=Stage.AUTHORITY_CLAIM, confidence=0.9,
                    )
                ]
            )
        }
    )
    assert conversation.source_text(spoken) == "CALLER: main CBI se bol raha hoon"

    # `partial` is in-flight ASR the contract calls "never scored" — a
    # half-finished sentence produces a label that flips as the rest arrives.
    partial_only = ocr.model_copy(update={"transcript": Transcript(final=[], partial="main CB")})
    assert conversation.source_text(partial_only) == "read off the screenshot"


def test_the_twin_forecasts_from_a_transcript_as_well_as_from_turns() -> None:
    """A transcript is a conversation whatever its length, so the two-turn floor
    that gates a pasted artefact does not apply to one."""
    from schema.models import Stage, Transcript, Utterance

    state = make_state("").model_copy(
        update={
            "inputs": [],
            "transcript": Transcript(
                final=[
                    Utterance(
                        id="u1", speaker="CALLER",
                        text="aap digital arrest par hain, kisi ko mat bataiye",
                        t0=0.0, t1=3.0, stage=Stage.ISOLATION, confidence=0.9,
                    )
                ]
            ),
        }
    )
    assert len(conversation.caller_turns(state)) < twin_min()
    done = investigate(state)
    forecast = by_agent(done).get(signals.DIGITAL_TWIN)
    assert forecast is not None and values(forecast, signals.F_NEXT_STAGE)


def test_stage_labels_and_the_peak_match_the_old_path() -> None:
    done = investigate(make_state(CALL))
    old = analyze_text(CALL)
    stage = by_agent(done)[signals.STAGE_CLASSIFIER]

    assert values(stage, signals.F_STAGE) == [ln.stage for ln in old.lines if ln.speaker == "CALLER"]

    expected_peak = max(
        (ln for ln in old.lines if ln.speaker == "CALLER"),
        key=lambda ln: stage_rank(ln.stage, ln.confidence),
    )
    peak = signals.first_finding(stage, signals.F_PEAK_STAGE)
    assert peak is not None
    assert peak.value == expected_peak.stage
    assert peak.confidence == pytest.approx(expected_peak.confidence, abs=1e-3)


def test_the_manipulation_map_matches_the_old_path() -> None:
    """The accumulator is rebuilt from published findings, not passed.

    `analyze_text` charges it caller-turn and victim-turn interleaved; the graph
    replays the caller's stages and then the victim's states, because two
    concurrent agents produce those halves and neither can hold the object. Every
    charge is `min(1.0, current + delta)` with non-negative deltas, so order does
    not matter — asserted here rather than argued.
    """
    done = investigate(make_state(CALL))
    old = analyze_text(CALL)
    fusion = by_agent(done)[signals.THREAT_FUSION]

    rebuilt = {
        key[len(signals.MANIPULATION_PREFIX):]: value
        for key, value in fusion.features.items()
        if key.startswith(signals.MANIPULATION_PREFIX)
    }
    assert rebuilt == old.manipulation_map


def test_the_coercion_index_matches_the_old_path() -> None:
    done = investigate(make_state(CALL))
    coercion = by_agent(done)[signals.COERCION_TRACKER]
    # `analyze_text` does not return the index directly, so it is reached the
    # same way the old path reaches it: the final victim turn's value.
    from services.api.engine.coercion import CoercionTracker

    tracker = CoercionTracker()
    expected = 0.0
    for speaker, text in normalise(CALL):
        if speaker == "VICTIM":
            expected = tracker.observe(text).index
    assert coercion.features[signals.K_COERCION_INDEX] == expected


def test_the_trust_percentage_and_the_checks_match_the_old_path() -> None:
    done = investigate(make_state(CALL))
    old = analyze_text(CALL)
    passport = by_agent(done)[signals.TRUST_PASSPORT]

    assert passport.features[signals.K_TRUST_PCT] == old.trust_passport["final_trust_pct"]
    assert sorted(values(passport, signals.F_PASSPORT_FAIL)) == sorted(
        c["name"] for c in old.trust_passport["checks"] if c["verdict"] == "FAIL"
    )


def test_the_script_similarity_matches_the_old_path() -> None:
    from services.api.engine.scripts import get_script_matcher

    done = investigate(make_state(CALL))
    script = by_agent(done)[signals.SCRIPT_MATCH]

    matcher = get_script_matcher()
    expected = max(
        matcher.match(text).similarity for speaker, text in normalise(CALL) if speaker == "CALLER"
    )
    assert script.features[signals.K_SCRIPT_SIMILARITY] == expected


def test_the_fused_drivers_match_the_old_path_one_for_one() -> None:
    """Driver-for-driver, not just the total.

    Two different weightings can reach the same score; the same drivers with the
    same contributions in the same order cannot happen by coincidence.
    """
    done = investigate(make_state(CALL))
    old = analyze_text(CALL)
    fusion = by_agent(done)[signals.THREAT_FUSION]

    drivers = [
        (f.value, f.confidence)
        for f in fusion.findings
        if f.label == signals.F_THREAT_DRIVER
    ]
    assert drivers == [(d["label"], d["contribution"]) for d in old.drivers]


@pytest.mark.parametrize("name", sorted(BENIGN))
def test_a_benign_message_scores_identically_through_both_paths(name: str) -> None:
    """Where no dispositive finding intervenes, the two paths are one number.

    This is the equivalence claim at full strength: not "the components agree"
    but "the score a citizen would be shown is the same one".
    """
    text = BENIGN[name]
    done = investigate(make_state(text))
    old = analyze_text(text)
    fusion = by_agent(done)[signals.THREAT_FUSION]

    assert old.findings == [] or all(f["verdict"] != "FAIL" for f in old.findings)
    assert fusion.features[signals.K_THREAT_SCORE] == old.score
    level = signals.first_finding(fusion, signals.F_THREAT_LEVEL)
    assert level is not None and level.value == old.level == "CALM"


def test_the_gap_to_the_old_paths_final_score_is_attributable() -> None:
    """Where the paths differ, the difference has a name.

    On this SMS `analyze_text` reaches 91 and the graph's fusion reaches 30.3.
    All of that gap is one finding — "Impersonates an institution", weight 0.9,
    produced by `engine/upi.py` against `refund@okaxis` — floored in by the
    dispositive rule. `upi.py` is task 2.6's Financial Fraud Agent and is not
    one of the seven modules 1.7 wraps, and the floor is a deterministic rule
    that ARCHITECTURE.md §4 places inside task 4.6's fusion. So the graph is not
    disagreeing with the engine; it is missing an agent and a rule, both named.
    """
    done = investigate(make_state(SCAM_SMS))
    old = analyze_text(SCAM_SMS)
    fusion = by_agent(done)[signals.THREAT_FUSION]
    fused = fusion.features[signals.K_THREAT_SCORE]

    assert fused < old.score, "the floor is not applied in the graph"
    floors = [55.0 + 40.0 * f["weight"] for f in old.findings if f["verdict"] == "FAIL"]
    assert floors, "this input no longer carries a dispositive finding"
    assert old.score == pytest.approx(max(max(floors), fused), abs=0.05)

    # And every one of them comes from a module 1.7 does not wrap: no passport
    # check failed here. If that stops being true, this test should fail rather
    # than the explanation quietly going stale.
    passport = by_agent(done)[signals.TRUST_PASSPORT]
    assert values(passport, signals.F_PASSPORT_FAIL) == []


# --------------------------------------------------------------------------
# Criterion 3 — the live path, and the graph, over the same call
# --------------------------------------------------------------------------


def test_the_live_session_and_the_graph_agree_on_the_call() -> None:
    """The same conversation, through the WebSocket engine and through the graph.

    The live path is `engine/session.py`, which owns the same components as
    stateful objects across a call. Nothing in 1.7 touched it; this asserts that
    it still runs and that it reaches the same stage labels the graph does, which
    is what "works through the new orchestrator and through the old path" means
    in practice.
    """
    from services.api.engine.session import Session

    session = Session(session_id="t_inherited")
    for speaker, text in normalise(CALL):
        session.ingest(text, speaker=speaker, duration_s=3.0)
    frame = session.frame()

    assert frame["threat"]["score"] > 0
    assert frame["stage"]["current"]

    done = investigate(make_state(CALL))
    graph_stages = values(by_agent(done)[signals.STAGE_CLASSIFIER], signals.F_STAGE)
    live_stages = [u.stage for u in session.utterances if u.speaker == "CALLER"]
    assert graph_stages == live_stages


def test_the_live_session_still_produces_an_evidence_package() -> None:
    """The inherited report path is untouched and still assembles."""
    from services.api.engine.report import build_evidence_package
    from services.api.engine.session import Session

    session = Session(session_id="t_inherited_report")
    for speaker, text in normalise(CALL):
        session.ingest(text, speaker=speaker, duration_s=3.0)

    package = build_evidence_package(session)
    assert package["report_id"].startswith("AGIS-")
    assert package["incident"]["peak_threat"] > 0
    assert package["reporting_guidance"]


# --------------------------------------------------------------------------
# Benign-input discipline — one per agent that can produce a signal
# --------------------------------------------------------------------------


def test_a_bank_reminder_naming_an_otp_is_not_a_credential_request() -> None:
    """The false positive that teaches people to ignore the system.

    "We will never ask for your OTP" mentions the credential in order to warn
    about it. Matching the bare word once flagged a real reminder call as
    CRITICAL.
    """
    done = investigate(make_state(BENIGN["bank otp reminder"]))
    passport = by_agent(done)[signals.TRUST_PASSPORT]
    assert "Credential request" not in values(passport, signals.F_PASSPORT_FAIL)
    assert passport.features[signals.K_PASSPORT_FAILS] == 0.0


@pytest.mark.parametrize("name", sorted(BENIGN))
def test_a_benign_line_never_reaches_the_script_gate(name: str) -> None:
    """Below `SCRIPT_MIN` the similarity contributes nothing, which is what
    stops shared vocabulary in an ordinary message from becoming a signal."""
    done = investigate(make_state(BENIGN[name]))
    script = by_agent(done)[signals.SCRIPT_MATCH]
    assert script.features[signals.K_SCRIPT_SIMILARITY] < SCRIPT_MIN


def test_an_ordinary_indian_mobile_fails_no_number_check() -> None:
    """Metadata a legitimate caller might have must not manufacture a verdict."""
    state = make_state(
        "Hi, this is Ramesh from the shop. Your order is ready for pickup.",
        entities={"phones": ["+919812345678"]},
    )
    result = run_one(signals.NUMBER_SPOOFING, state)
    assert result.status is AgentStatus.OK
    assert values(result, signals.F_NUMBER_FAIL) == []
    assert result.features[signals.K_SPOOFING_RISK] == 0.0


@pytest.mark.parametrize("name", sorted(BENIGN))
def test_a_benign_message_is_scored_only_by_what_was_not_checked(name: str) -> None:
    """The one driver a clean message produces is about *us*, not about it.

    "Identity unverified" is the Trust Passport reading 50% because nothing
    resolved either way — an honest 7.5 points for an unverified caller. What
    matters is that no driver names anything the message did: no stage, no
    manipulation pressure, no script match, no victim stress. A benign SMS that
    produced a content driver would be the false positive this project treats as
    a first-class failure.

    Parametrised over every benign fixture, because checking one of them is how
    this got through: with the promoted checkpoint serving, `sbi debit alert`
    produced "Stage: Verification Demand" as well, and no assertion was pointed
    at it. See `test_an_unsure_stage_label_cannot_outrank_a_confident_benign`
    for the rule that caused it.
    """
    done = investigate(make_state(BENIGN[name]))
    fusion = by_agent(done)[signals.THREAT_FUSION]

    assert fusion.features[signals.K_THREAT_SCORE] < 25.0
    assert values(fusion, signals.F_THREAT_DRIVER) == ["Identity unverified"]
    assert fusion.features[signals.K_TACTIC_PRESSURE] == 0.0


def test_an_unsure_stage_label_cannot_outrank_a_confident_benign() -> None:
    """The rule that made two of the three benign fixtures name a scam stage.

    `threat_weight("BENIGN")` is 0, so before the floor existed *any* non-benign
    label at *any* confidence out-ranked a BENIGN the classifier was sure of: a
    0.242 VERIFICATION_DEMAND became the peak over a 0.553 BENIGN on an Amazon
    delivery notice, and the peak is what `fuse()` scores and then names in the
    report. Below `MIN_STAGE_CONFIDENCE` the rank is 0, so an unsure label can
    neither become the peak nor contribute points.

    The confidences here are the measured ones, not invented: 0.242 and 0.266
    are what the promoted checkpoint produces on the benign fixtures, and 0.601
    to 0.911 is the band the turns carrying a scam verdict occupy.
    """
    assert stage_rank("VERIFICATION_DEMAND", 0.242) == 0.0
    assert stage_rank("VERIFICATION_DEMAND", 0.266) == 0.0
    assert stage_rank("GREETING", 0.340) == 0.0

    # Above the floor the old product stands unchanged — this is a floor, not
    # a rescaling, so every score that was already attributable still is.
    assert stage_rank("ISOLATION", 0.911) == threat_weight("ISOLATION") * 0.911
    assert stage_rank("VERIFICATION_DEMAND", 0.601) == threat_weight("VERIFICATION_DEMAND") * 0.601
    assert stage_rank("ISOLATION", 0.911) > stage_rank("VERIFICATION_DEMAND", 0.601) > 0.0

    # BENIGN is weightless either way; the floor is not what silences it.
    assert stage_rank("BENIGN", 0.999) == 0.0
    assert MIN_STAGE_CONFIDENCE > 0.340


def test_an_unsure_stage_adds_no_points_not_merely_no_driver() -> None:
    """`fuse()` opens by promising every point is attributable.

    Suppressing the driver while still adding its component to `raw` would keep
    the report clean and leave the number wrong — points on the meter that no
    named driver accounts for. The floor zeroes the component, so the score a
    sub-threshold stage produces is the score no stage at all produces.
    """
    def fused(stage: str, confidence: float):
        return fuse(
            stage=stage,
            stage_confidence=confidence,
            manipulation=ManipulationAccumulator(),
            coercion_index=0.0,
            trust_pct=None,
        )

    unsure = fused("VERIFICATION_DEMAND", 0.242)
    absent = fused("BENIGN", 0.242)

    assert unsure.score == absent.score
    assert [d.label for d in unsure.drivers] == [d.label for d in absent.drivers]

    # And the same label above the floor does still score and still explain.
    sure = fused("VERIFICATION_DEMAND", 0.601)
    assert sure.score > unsure.score
    assert "Stage: Verification Demand" in [d.label for d in sure.drivers]


# --------------------------------------------------------------------------
# The spoofing agent, and the reason SKIPPED may not read as clean
# --------------------------------------------------------------------------


def test_the_spoofing_agent_matches_the_engine_on_a_foreign_authority_claim() -> None:
    state = make_state(CALL, entities={"phones": ["+1-838-224-7719"]})
    done = investigate(state)
    result = by_agent(done)[signals.NUMBER_SPOOFING]

    expected = analyze_number("+1-838-224-7719", claimed_identity=CALL)
    assert result.features[signals.K_SPOOFING_RISK] == round(expected.risk, 1)
    assert sorted(values(result, signals.F_NUMBER_FAIL)) == sorted(
        c.name for c in expected.checks if c.verdict == "FAIL"
    )
    assert result.features[signals.K_SPOOFING_RISK] > 0


def test_a_number_arriving_as_its_own_evidence_item_is_investigated() -> None:
    """The route a submission actually takes today, with no entity extraction."""
    state = make_state(CALL)
    state = state.model_copy(
        update={
            "inputs": [
                *state.inputs,
                EvidenceItem(id="ev-02", kind=InputType.PHONE, text="+919812345678"),
            ]
        }
    )
    assert conversation.phone_numbers(state) == ["+919812345678"]
    assert registry.get(signals.NUMBER_SPOOFING).can_handle(state)

    # And the number does not become a conversational turn.
    assert all("+919812345678" not in t.text for t in conversation.turns(state))


def test_an_absent_number_is_carried_as_unmeasured_and_not_as_clean() -> None:
    """`threat.fuse` types `spoofing_risk` Optional for a reason worth keeping.

    "An absent number is not a clean number, so `None` contributes nothing
    rather than reading as safe." In today's arithmetic 0.0 and None happen to
    produce the same zero, so the difference is not in the score — it is in what
    the fusion *claims to have had*, which is what a reader and 4.1 both act on.
    This pins the three places that claim is visible, and the mechanism
    (`signals.feature` refusing to read a result that did not answer) that keeps
    a fabricated 0.0 from getting there in the first place.
    """
    state = make_state(CALL)
    assert not registry.get(signals.NUMBER_SPOOFING).can_handle(state)

    done = investigate(state)
    produced = by_agent(done)
    assert signals.NUMBER_SPOOFING not in produced

    # 1. The value the fusion agent reads is None, not zero.
    absent = signals.result_of(done, signals.NUMBER_SPOOFING)
    assert signals.feature(absent, signals.K_SPOOFING_RISK) is None

    # 2. The fusion does not list a signal it did not have.
    fusion = produced[signals.THREAT_FUSION]
    assert signals.NUMBER_SPOOFING not in fusion.provenance

    # 3. And it says how much it had: four signals of five.
    assert fusion.confidence == pytest.approx(0.8)

    with_number = by_agent(
        investigate(make_state(CALL, entities={"phones": ["+1-838-224-7719"]}))
    )[signals.THREAT_FUSION]
    assert signals.NUMBER_SPOOFING in with_number.provenance
    assert with_number.confidence == pytest.approx(1.0)
    assert (
        with_number.features[signals.K_THREAT_SCORE]
        > fusion.features[signals.K_THREAT_SCORE]
    ), "a spoofed number should raise the score, not merely be recorded"


# --------------------------------------------------------------------------
# Degradation paths, each exercised
# --------------------------------------------------------------------------


def test_the_coercion_index_is_text_only_and_says_so() -> None:
    """No audio means no prosodic half, so the index is capped and tagged.

    A text-only stress estimate must never be able to reach the same ceiling as
    one backed by pitch variance and pause ratio.
    """
    from services.api.engine.coercion import TEXT_ONLY_CEILING

    done = investigate(make_state(CALL))
    coercion = by_agent(done)[signals.COERCION_TRACKER]

    assert coercion.status is AgentStatus.DEGRADED
    assert "coercion:text_only" in (coercion.error or "")
    assert coercion.features[signals.K_COERCION_INDEX] <= TEXT_ONLY_CEILING
    assert "agent:coercion_tracker:degraded" in done.degraded


def test_the_coercion_agent_skips_a_one_sided_message() -> None:
    state = make_state(SCAM_SMS)
    assert conversation.victim_turns(state) == []
    assert not registry.get(signals.COERCION_TRACKER).can_handle(state)
    assert signals.COERCION_TRACKER not in by_agent(investigate(state))


def test_the_twin_falls_back_to_the_prior_when_the_matrix_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.api.agents.inherited import twin as twin_agent
    from services.api.engine.twin import DigitalTwin

    monkeypatch.setattr(
        twin_agent, "DigitalTwin", lambda: DigitalTwin(path=pathlib.Path("/nonexistent.json"))
    )
    done = investigate(make_state(CALL))
    forecast = by_agent(done)[signals.DIGITAL_TWIN]

    assert forecast.status is AgentStatus.DEGRADED
    assert "twin:prior_only" in (forecast.error or "")
    assert forecast.provenance == ["twin:canonical_prior"]
    assert values(forecast, signals.F_NEXT_STAGE), "the prior still answers"


def test_the_twin_skips_an_artefact_rather_than_forecasting_one() -> None:
    """"What will the scammer do next" is a question about a conversation."""
    state = make_state("Your KYC is suspended.")
    assert len(conversation.caller_turns(state)) < twin_min()
    assert not registry.get(signals.DIGITAL_TWIN).can_handle(state)
    assert signals.DIGITAL_TWIN not in by_agent(investigate(state))


def twin_min() -> int:
    from services.api.agents.inherited.twin import MIN_CALLER_TURNS

    return MIN_CALLER_TURNS


def test_the_stage_classifier_reports_a_genuine_fallback_as_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`serving_is_fallback`, never `backend != "muril"`.

    The fused backend serves MuRIL's weights under the name "fused", so a
    string comparison reports degradation while the checkpoint is demonstrably
    in memory — the confident-but-wrong answer /api/health was fixed for.
    """
    from services.api.engine import classifier as classifier_mod

    monkeypatch.setattr(classifier_mod, "serving_is_fallback", True)
    degraded = by_agent(investigate(make_state(CALL)))[signals.STAGE_CLASSIFIER]
    assert degraded.status is AgentStatus.DEGRADED

    monkeypatch.setattr(classifier_mod, "serving_is_fallback", False)
    promoted = by_agent(investigate(make_state(CALL)))[signals.STAGE_CLASSIFIER]
    assert promoted.status is AgentStatus.OK
    assert values(promoted, signals.F_STAGE) == values(degraded, signals.F_STAGE)


def test_fusion_degrades_only_when_a_contributing_agent_actually_failed() -> None:
    """A signal that does not apply is not a shortfall.

    A forwarded SMS has no victim side. Marking every SMS investigation degraded
    for it would produce a `degraded` field people learn to ignore, which is
    worse than no field at all.
    """
    sms = by_agent(investigate(make_state(SCAM_SMS)))[signals.THREAT_FUSION]
    assert signals.COERCION_TRACKER not in sms.provenance
    assert sms.status is AgentStatus.OK
    assert sms.confidence < 1.0, "coverage is what says a signal was missing"

    call = by_agent(investigate(make_state(CALL)))[signals.THREAT_FUSION]
    assert signals.COERCION_TRACKER in call.provenance
    assert call.confidence > sms.confidence


def test_fusion_declines_to_score_with_nothing_classified() -> None:
    """No stage, no fusion — a confident zero is the shape of a false negative."""
    empty = make_state("")
    empty = empty.model_copy(update={"inputs": []})
    assert not registry.get(signals.THREAT_FUSION).can_handle(empty)


def test_an_agent_that_raises_does_not_take_the_investigation_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The degradation invariant, at the tier the engine now occupies."""
    from services.api.agents.inherited import script as script_agent

    def explode() -> None:
        raise RuntimeError("matcher is unwell")

    monkeypatch.setattr(script_agent, "get_script_matcher", explode)
    done = investigate(make_state(CALL))

    assert by_agent(done)[signals.SCRIPT_MATCH].status is AgentStatus.ERROR
    assert "agent:script_match:error" in done.degraded
    # The investigation still completed, and still fused — over four signals
    # instead of five, which `provenance` says out loud.
    fusion = by_agent(done)[signals.THREAT_FUSION]
    assert signals.SCRIPT_MATCH not in fusion.provenance
    assert fusion.status is AgentStatus.DEGRADED
    assert signals.SCRIPT_MATCH in (fusion.error or "")
    assert done.status.value == "COMPLETE"


# --------------------------------------------------------------------------
# The signals contract between the tiers
# --------------------------------------------------------------------------


def test_every_feature_the_fusion_agent_reads_is_actually_published() -> None:
    """A key that stops being emitted contributes zero and says nothing.

    That is the drift `signals.py` exists to prevent, and this is the test that
    notices — the two sides import the same constants, so a rename fails here
    rather than becoming a signal that quietly disappeared.
    """
    state = make_state(CALL, entities={"phones": ["+1-838-224-7719"]})
    produced = by_agent(investigate(state))

    expected = {
        signals.STAGE_CLASSIFIER: [signals.K_STAGE_CONFIDENCE, signals.K_CALLER_TURNS],
        signals.COERCION_TRACKER: [signals.K_COERCION_INDEX, signals.K_VICTIM_TURNS],
        signals.TRUST_PASSPORT: [signals.K_TRUST_PCT, signals.K_PASSPORT_FAILS],
        signals.SCRIPT_MATCH: [signals.K_SCRIPT_SIMILARITY],
        signals.NUMBER_SPOOFING: [signals.K_SPOOFING_RISK, signals.K_NUMBER_FAILS],
        signals.DIGITAL_TWIN: [signals.K_FORECAST_PROBABILITY, signals.K_ETA_S],
        signals.THREAT_FUSION: [signals.K_THREAT_SCORE, signals.K_TACTIC_PRESSURE],
    }
    for agent, keys in expected.items():
        assert agent in produced, f"{agent} did not run"
        for key in keys:
            assert key in produced[agent].features, f"{agent} stopped publishing {key}"

    assert signals.first_finding(produced[signals.STAGE_CLASSIFIER], signals.F_PEAK_STAGE)
    assert signals.first_finding(produced[signals.SCRIPT_MATCH], signals.F_SCRIPT_MATCH)
    assert signals.first_finding(produced[signals.DIGITAL_TWIN], signals.F_NEXT_STAGE)
    assert signals.first_finding(produced[signals.THREAT_FUSION], signals.F_THREAT_LEVEL)


def test_a_skipped_or_failed_result_reads_as_no_answer() -> None:
    """`answered()` is what keeps an unrun check out of the weighted sum."""
    for status in (AgentStatus.SKIPPED, AgentStatus.ERROR):
        result = AgentResult(agent="x", version="1.0.0", status=status, features={"k": 1.0})
        assert signals.answered(result) is False
        assert signals.feature(result, "k") is None
    for status in (AgentStatus.OK, AgentStatus.DEGRADED):
        result = AgentResult(agent="x", version="1.0.0", status=status, features={"k": 1.0})
        assert signals.answered(result) is True
        assert signals.feature(result, "k") == 1.0


def test_the_investigation_is_reproducible_across_runs() -> None:
    """Same input, same fingerprint — the property the Phase 9 ablations rest on,
    now that seven more agents contribute to it."""
    first = investigate(make_state(CALL))
    second = investigate(make_state(CALL))
    assert orch.fingerprint(first) == orch.fingerprint(second)
