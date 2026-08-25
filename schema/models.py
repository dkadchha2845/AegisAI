"""
AegisAI — the WebSocket contract. Single source of truth.

Both sides build against this file: the backend emits these models, the
frontend renders `types.ts` which mirrors them exactly. Nothing else crosses
the boundary.

Three design decisions worth understanding before changing anything here
=======================================================================

1. STATE SNAPSHOT vs DISCRETE EVENT — the important one.

   `StateFrame` is a complete picture of the call at time t. It is idempotent:
   receiving the same frame twice changes nothing, and a client that missed
   ten frames is fully correct after the next one. This is what makes the
   demo survive a dropped socket on stage.

   `Event` is a one-shot edge: the guardian alert fired, the payment was held,
   the threat crossed into HIGH. Animations need edges, not levels. Deriving
   "did it just cross 70?" by diffing consecutive snapshots is fragile —
   frames drop, arrive twice, or arrive out of order, and the meter shakes
   twice or never. So the backend, which knows the truth, emits the edge.

2. The frontend is a PURE RENDERER.

   No threat maths, no thresholds, no stage logic in React. Every number the
   UI shows is a field here. If the UI needs to display something, it becomes
   a field rather than a calculation — otherwise the same logic drifts apart
   in two languages.

3. Every score carries its provenance.

   `ThreatState.drivers` and `TrustPassport.checks` exist so the UI can always
   answer "why?". A threat meter that reads 91 with no explanation is a demo;
   one that reads 91 *because* of three named signals is a product, and it is
   what survives a judge asking how it works.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

CONTRACT_VERSION = 1


# --------------------------------------------------------------------------
# Enums — mirrored verbatim in types.ts
# --------------------------------------------------------------------------


class Stage(str, Enum):
    GREETING = "GREETING"
    AUTHORITY_CLAIM = "AUTHORITY_CLAIM"
    FEAR_INDUCTION = "FEAR_INDUCTION"
    ISOLATION = "ISOLATION"
    VERIFICATION_DEMAND = "VERIFICATION_DEMAND"
    PAYMENT_SETUP = "PAYMENT_SETUP"
    PAYMENT_EXECUTION = "PAYMENT_EXECUTION"
    BENIGN = "BENIGN"


class ThreatLevel(str, Enum):
    """Bands, not raw score. The UI keys colour and motion off the band so a
    score wobbling around 69/71 doesn't flicker the whole interface."""

    CALM = "CALM"          # 0-24
    WATCH = "WATCH"        # 25-49
    ELEVATED = "ELEVATED"  # 50-69
    HIGH = "HIGH"          # 70-89
    CRITICAL = "CRITICAL"  # 90-100


class VictimState(str, Enum):
    UNKNOWN = "UNKNOWN"
    CALM = "CALM"
    CONFUSED = "CONFUSED"
    ANXIOUS = "ANXIOUS"
    PANICKED = "PANICKED"
    COMPLIANT = "COMPLIANT"
    RESISTING = "RESISTING"


class PaymentState(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    HELD = "HELD"          # circuit-breaker fired
    CANCELLED = "CANCELLED"
    APPROVED = "APPROVED"


class GuardianState(str, Enum):
    IDLE = "IDLE"
    ALERTING = "ALERTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CALLING = "CALLING"


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


# --------------------------------------------------------------------------
# Sub-structures
# --------------------------------------------------------------------------


class Utterance(BaseModel):
    id: str
    speaker: Literal["CALLER", "VICTIM"]
    text: str
    t0: float = Field(description="seconds from call start")
    t1: float
    stage: Stage
    confidence: float = Field(ge=0, le=1)
    victim_state: VictimState = VictimState.UNKNOWN


class Transcript(BaseModel):
    final: list[Utterance] = Field(default_factory=list)
    # In-flight ASR text, not yet classified. Rendered dimmed; never scored.
    partial: Optional[str] = None
    partial_speaker: Optional[Literal["CALLER", "VICTIM"]] = None


class StageState(BaseModel):
    current: Stage
    confidence: float = Field(ge=0, le=1)
    since_s: float = Field(description="seconds spent in this stage so far")
    # Full distribution so the UI can show runner-up stages, and so a judge
    # asking "how sure is it?" gets a real answer instead of one number.
    distribution: dict[Stage, float] = Field(default_factory=dict)


class CoercionState(BaseModel):
    """Audio-side victim stress. Deliberately separate from the text classifier
    so the two are independent signals — that independence is what the fusion
    ablation in the deck demonstrates."""

    index: float = Field(ge=0, le=100)
    trend: Literal["rising", "falling", "flat"]
    history: list[float] = Field(
        default_factory=list, description="recent values, for the sparkline"
    )
    features: dict[str, float] = Field(
        default_factory=dict,
        description="pause_ratio, speech_rate_wpm, pitch_var, compliance_hits",
    )


class ThreatDriver(BaseModel):
    """One named reason the score is what it is."""

    label: str
    contribution: float = Field(ge=0, le=1)
    detail: str


class ThreatState(BaseModel):
    score: float = Field(ge=0, le=100)
    level: ThreatLevel
    drivers: list[ThreatDriver] = Field(default_factory=list)


class ManipulationMap(BaseModel):
    """Cumulative tactic pressure, 0-1 each. Bars fill over the call."""

    authority: float = Field(0.0, ge=0, le=1)
    fear: float = Field(0.0, ge=0, le=1)
    isolation: float = Field(0.0, ge=0, le=1)
    urgency: float = Field(0.0, ge=0, le=1)
    compliance: float = Field(0.0, ge=0, le=1)


class Forecast(BaseModel):
    """The Digital Twin. Beat 3 of the demo, and the reason anyone remembers it.

    `eta_s` is when the next stage is expected; `eta_to_payment_s` is the
    headline number — how long until money moves if nobody intervenes.
    """

    next_stage: Stage
    probability: float = Field(ge=0, le=1)
    eta_s: float
    eta_to_payment_s: Optional[float] = None
    # Set once the predicted stage actually occurs. This is what lets the UI
    # show "we called it" — a forecast nobody scores is just a guess.
    last_prediction_correct: Optional[bool] = None


class PassportCheck(BaseModel):
    name: str
    verdict: Verdict
    detail: str
    source: Optional[str] = Field(
        None, description="RAG citation — which document backed this check"
    )


class TrustPassport(BaseModel):
    claimed_identity: Optional[str] = None
    final_trust_pct: float = Field(ge=0, le=100)
    checks: list[PassportCheck] = Field(default_factory=list)


class NumberIntel(BaseModel):
    """Caller-number intelligence — the metadata half of a verdict.

    Reuses `PassportCheck` for its rows so the UI renders both with one
    component: same PASS/FAIL/UNKNOWN grammar, same citation discipline.
    `risk` runs the opposite direction to the passport's trust percentage —
    higher means more likely spoofed — because the number is evidence *against*
    a caller, where the passport measures evidence *for* them.
    """

    number: Optional[str] = None
    risk: float = Field(ge=0, le=100)
    verdict: Verdict
    checks: list[PassportCheck] = Field(default_factory=list)


class CoachSuggestion(BaseModel):
    """Retrieved, never generated at runtime. `line` comes from a curated,
    safety-reviewed library so nothing unvetted is ever put in a frightened
    person's mouth."""

    line: str
    tactic: str
    why: str
    sources: list[str] = Field(default_factory=list)
    urgency: Literal["info", "warn", "urgent"] = "info"


class Narration(BaseModel):
    """Plain-language account of what the system is doing, and why.

    A contract field rather than frontend copy, for the same reason every
    other number is one: the explanation has to agree with the score it is
    explaining. Two implementations of "what is happening right now" would
    drift apart exactly like two implementations of the threat maths, except
    the disagreement would be in prose and nobody would notice until a judge
    read the panel and the meter in the same glance.

    `sources` cites the knowledge-base sections behind the claim, so the
    narration is auditable rather than merely fluent.
    """

    headline: str
    detail: str
    sources: list[str] = Field(default_factory=list)


class GuardianInfo(BaseModel):
    state: GuardianState = GuardianState.IDLE
    name: Optional[str] = None
    alerted_at_s: Optional[float] = None
    acknowledged_at_s: Optional[float] = None


class PaymentInfo(BaseModel):
    state: PaymentState = PaymentState.NONE
    amount_inr: Optional[float] = None
    payee: Optional[str] = None
    held_reason: Optional[str] = None
    held_at_s: Optional[float] = None


class CallInfo(BaseModel):
    status: Literal["idle", "active", "ended"] = "idle"
    duration_s: float = 0.0
    caller_number: Optional[str] = None
    started_at: Optional[str] = None


# --------------------------------------------------------------------------
# The two message types
# --------------------------------------------------------------------------


class StateFrame(BaseModel):
    """Complete call state. Idempotent — safe to drop, replay, or reorder."""

    v: int = CONTRACT_VERSION
    type: Literal["state"] = "state"
    session_id: str
    seq: int
    t: float = Field(description="seconds since call start")

    call: CallInfo = Field(default_factory=CallInfo)
    transcript: Transcript = Field(default_factory=Transcript)
    stage: Optional[StageState] = None
    coercion: Optional[CoercionState] = None
    threat: Optional[ThreatState] = None
    manipulation_map: ManipulationMap = Field(default_factory=ManipulationMap)
    forecast: Optional[Forecast] = None
    trust_passport: Optional[TrustPassport] = None
    number_intel: Optional[NumberIntel] = None
    coach: Optional[CoachSuggestion] = None
    narration: Optional[Narration] = None
    guardian: GuardianInfo = Field(default_factory=GuardianInfo)
    payment: PaymentInfo = Field(default_factory=PaymentInfo)

    # Degradation is explicit, never silent. If ASR fell back to local
    # whisper or the classifier is cold, the UI can say so rather than
    # showing a confident-looking number built on nothing.
    degraded: list[str] = Field(default_factory=list)


class EventKind(str, Enum):
    THRESHOLD_CROSSED = "THRESHOLD_CROSSED"
    STAGE_CHANGED = "STAGE_CHANGED"
    FORECAST_HIT = "FORECAST_HIT"        # the twin called it correctly
    GUARDIAN_ALERTED = "GUARDIAN_ALERTED"
    GUARDIAN_ACKNOWLEDGED = "GUARDIAN_ACKNOWLEDGED"
    PAYMENT_ATTEMPTED = "PAYMENT_ATTEMPTED"
    PAYMENT_HELD = "PAYMENT_HELD"
    PAYMENT_CANCELLED = "PAYMENT_CANCELLED"
    COACH_URGENT = "COACH_URGENT"
    CALL_ENDED = "CALL_ENDED"


class Event(BaseModel):
    """A discrete edge. Fire-and-forget; the UI animates off these."""

    v: int = CONTRACT_VERSION
    type: Literal["event"] = "event"
    session_id: str
    seq: int
    t: float
    kind: EventKind
    payload: dict = Field(default_factory=dict)


class ErrorMessage(BaseModel):
    v: int = CONTRACT_VERSION
    type: Literal["error"] = "error"
    session_id: Optional[str] = None
    code: str
    message: str
    recoverable: bool = True


# --------------------------------------------------------------------------
# Client -> server
# --------------------------------------------------------------------------


class ClientCommand(BaseModel):
    """Everything the browser can ask for. Audio rides as binary frames."""

    v: int = CONTRACT_VERSION
    type: Literal["command"] = "command"
    action: Literal[
        "start_session",
        "end_session",
        "inject_text",        # demo fallback when live audio fails
        "guardian_ack",
        "guardian_cancel_payment",
        "guardian_approve_payment",
        "attempt_payment",
        "replay_demo",
    ]
    payload: dict = Field(default_factory=dict)


def threat_level(score: float) -> ThreatLevel:
    """Single definition of the bands. Backend uses it; the UI reads the
    resulting field and never recomputes it."""
    if score >= 90:
        return ThreatLevel.CRITICAL
    if score >= 70:
        return ThreatLevel.HIGH
    if score >= 50:
        return ThreatLevel.ELEVATED
    if score >= 25:
        return ThreatLevel.WATCH
    return ThreatLevel.CALM


# ===========================================================================
# THE INVESTIGATION CONTRACT
# ===========================================================================
#
# Everything above this line is the *live call* contract: a 4 Hz stream of
# idempotent `StateFrame` snapshots and discrete `Event` edges, designed for a
# socket that may drop.
#
# Everything below is the *investigation* contract from ARCHITECTURE.md §3 —
# one evidence submission travelling through the agent graph. Different shape,
# different lifetime: an investigation is a single object that accumulates
# agent results over seconds to minutes, is persisted, and is re-read later.
#
# They share this file on purpose. Two contract files become two vocabularies:
# one would grow its own `ThreatLevel` with different bands, and the number a
# citizen sees during a live call would stop meaning what the number on their
# report means. So `InvestigationState` reuses `ThreatLevel`, `Transcript`,
# `Stage` and `Verdict` verbatim rather than restating them.
#
# The two versions are separate, though, because they evolve independently:
# adding a field to the investigation must not invalidate a mobile client that
# only speaks the frame contract.

INVESTIGATION_CONTRACT_VERSION = 1


# --------------------------------------------------------------------------
# Investigation enums — mirrored verbatim in types.ts
# --------------------------------------------------------------------------


class InputType(str, Enum):
    """What a piece of evidence *is*, as decided by the input classifier.

    Determined by magic bytes first, extension second, content third — never
    by the user-supplied MIME type (task 1.4). One evidence item may carry
    several types: a screenshot is both IMAGE and SCREENSHOT, and an `.eml`
    with a PDF attachment yields EMAIL and PDF. Ambiguity is expressed by
    returning more than one type, never by guessing one.

    UNKNOWN is a routing decision, not a failure: it sends the item to the
    text agent, which is the only agent that can safely accept anything.
    """

    TEXT = "TEXT"
    SMS = "SMS"
    EMAIL = "EMAIL"
    IMAGE = "IMAGE"
    SCREENSHOT = "SCREENSHOT"
    PDF = "PDF"
    DOCUMENT = "DOCUMENT"
    URL = "URL"
    APK = "APK"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    QR = "QR"
    PHONE = "PHONE"
    UPI_ID = "UPI_ID"
    UNKNOWN = "UNKNOWN"


class AgentStatus(str, Enum):
    """The four outcomes of running one agent, and the whole reason the
    degradation invariant is checkable.

    DEGRADED is the important one: the agent answered, but from a fallback —
    a cached threat-intel snapshot instead of the live feed, Tesseract instead
    of PaddleOCR. The answer is usable and the shortfall is visible. SKIPPED
    means the agent was not applicable (an APK agent on an audio file), which
    must never be read as "clean" by the feature assembly in 4.1.
    """

    OK = "ok"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    ERROR = "error"


class InvestigationStatus(str, Enum):
    """Lifecycle of the investigation itself, as the API in 1.6 reports it."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FraudCategory(str, Enum):
    """The twelve categories of DATASETS.md §3, plus the hard negative.

    Slugs match the dataset's `category` field exactly, so a corpus item and a
    live classification are the same string — otherwise the Phase 4 training
    join needs a mapping table, and mapping tables rot.

    There is no UNKNOWN member. `classification` is Optional; `None` means
    "not classified yet", and BENIGN means "classified, and it is legitimate".
    Collapsing those two into one value would let an unfinished investigation
    read as a cleared one.
    """

    DIGITAL_ARREST = "digital_arrest"
    BANKING_IMPERSONATION = "banking_impersonation"
    UPI_PAYMENT_FRAUD = "upi_payment_fraud"
    PHISHING = "phishing"
    OTP_HARVESTING = "otp_harvesting"
    COURIER_CUSTOMS = "courier_customs"
    JOB_TASK_SCAM = "job_task_scam"
    INVESTMENT_TRADING = "investment_trading"
    LOAN_APP = "loan_app"
    SUPPORT_IMPERSONATION = "support_impersonation"
    REMOTE_ACCESS = "remote_access"
    LOTTERY_REWARD = "lottery_reward"
    BENIGN = "benign"


class Severity(str, Enum):
    """One ordered scale, shared by evidence findings and recommendations.

    Shared deliberately: the report renders findings and the actions they
    imply in a single ranked column, and two scales would have to be reconciled
    in the UI — which is exactly the frontend arithmetic the contract exists to
    prevent.
    """

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecommendedAction(str, Enum):
    """A closed vocabulary of things we tell a citizen to do.

    Closed on purpose, for the same reason `CoachSuggestion.line` is retrieved
    from a reviewed library rather than generated: advice given to a frightened
    person under pressure is a safety surface. The LLM may rank and explain
    these; it may not invent a fifteenth one. `detail` carries the specifics
    (which number, which bank), and is the only free text.

    The membership is not invented — it is the vocabulary the system already
    ships. Every line `engine/analyzer.py::_actions()` can produce maps onto a
    member here, and `test_investigation_contract.py` fails if one stops doing
    so. That test is what caught END_THE_CALL, DO_NOT_ACT_YET and
    PROVIDE_MORE_EVIDENCE missing from the first draft of this enum: the running
    system had been telling people "hang up" since long before the contract
    existed, and a closed vocabulary that cannot say it is not closed, it is
    incomplete.
    """

    DO_NOT_PAY = "DO_NOT_PAY"
    DO_NOT_SHARE_OTP = "DO_NOT_SHARE_OTP"
    DO_NOT_OPEN_LINK = "DO_NOT_OPEN_LINK"
    DO_NOT_INSTALL_APP = "DO_NOT_INSTALL_APP"
    DO_NOT_ACT_YET = "DO_NOT_ACT_YET"
    END_THE_CALL = "END_THE_CALL"
    VERIFY_VIA_OFFICIAL_CHANNEL = "VERIFY_VIA_OFFICIAL_CHANNEL"
    CONTACT_YOUR_BANK = "CONTACT_YOUR_BANK"
    BLOCK_AND_REPORT_NUMBER = "BLOCK_AND_REPORT_NUMBER"
    REPORT_TO_CYBERCRIME = "REPORT_TO_CYBERCRIME"
    PRESERVE_EVIDENCE = "PRESERVE_EVIDENCE"
    SEEK_HELP_FROM_TRUSTED_PERSON = "SEEK_HELP_FROM_TRUSTED_PERSON"
    PROVIDE_MORE_EVIDENCE = "PROVIDE_MORE_EVIDENCE"
    NO_ACTION_NEEDED = "NO_ACTION_NEEDED"


# --------------------------------------------------------------------------
# Investigation sub-structures
# --------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """One submitted artefact. Never the bytes themselves.

    `uri` points at object storage; `text` inlines only payloads that are
    genuinely small and textual (a pasted message, a URL, a phone number).
    Keeping bytes out of the state object is what lets the whole state be
    persisted as JSONB, streamed to the UI, and attached to a trace without
    a 4 MB screenshot riding along on every hop.

    `declared_type` records what the uploader *claimed*, next to `media_type`,
    which is what the magic bytes actually say. Both are kept because their
    disagreement is itself a signal — an APK renamed `.jpg` is a finding, and
    it can only be a finding if we wrote down the lie.
    """

    id: str
    kind: InputType = InputType.UNKNOWN
    filename: Optional[str] = None
    declared_type: Optional[str] = Field(
        None, description="user-supplied MIME — recorded, never trusted for routing"
    )
    media_type: Optional[str] = Field(
        None, description="type detected from magic bytes"
    )
    size_bytes: Optional[int] = Field(None, ge=0)
    sha256: Optional[str] = None
    uri: Optional[str] = Field(None, description="object-store reference")
    text: Optional[str] = Field(
        None, description="inline payload for small textual evidence only"
    )
    received_at: Optional[str] = Field(
        None, description="ISO-8601 UTC"
    )


class ExtractedText(BaseModel):
    """Text recovered from one evidence item, and how it was recovered.

    `extractor` is not decoration: OCR at 0.62 confidence and a verbatim paste
    at 1.0 are different evidence, and the report has to be able to say which
    it is standing on. `source_ref` is an `EvidenceItem.id`, so every claim
    downstream can be walked back to the artefact it came from.
    """

    source_ref: str = Field(description="EvidenceItem.id this text came from")
    text: str
    language: Optional[str] = Field(
        None, description="'en' | 'hi' | 'hi-Latn' (Hinglish) | None if undetected"
    )
    confidence: float = Field(1.0, ge=0, le=1)
    extractor: str = Field(
        description="'verbatim' | 'ocr:paddle' | 'ocr:tesseract' | 'asr:faster-whisper' | ..."
    )


class EntitySet(BaseModel):
    """Every identifier the investigation has found, flat and deduplicated.

    Field names match `services/api/intel/entities.ExtractedEntities` exactly.
    That is a hard requirement, not a courtesy: the knowledge graph keys nodes
    off these names, and a contract that said `accounts` where the graph says
    `bank_accounts` would silently drop a whole entity class at the boundary in
    Phase 3.

    The first ten fields are *linkable* — two cases sharing one are two cases
    connected. `banks`, `locations` and `scam_keywords` are display context and
    must never become graph edges: two cases both naming "SBI" are not related
    by that fact, and drawing that edge would manufacture a fraud network out
    of a common noun.
    """

    phones: list[str] = Field(default_factory=list)
    upi_ids: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    wallets: list[str] = Field(default_factory=list)
    bank_accounts: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    ips: list[str] = Field(default_factory=list)
    apps: list[str] = Field(
        default_factory=list, description="package names or app names named in evidence"
    )
    orgs: list[str] = Field(default_factory=list)

    amounts: list[float] = Field(default_factory=list)
    authorities: list[str] = Field(
        default_factory=list, description="institutions the sender claims to be"
    )
    # --- display context only; never graph edges ---
    banks: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    scam_keywords: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    """One thing an agent observed. Machine-facing and cheap.

    Distinct from `EvidenceFinding` below, which is the ranked, citizen-facing
    item that appears in a report. An agent emits many small Findings; the
    fusion and explainability agents promote a handful of them to evidence.
    Keeping the two apart is what stops the report becoming a log dump.
    """

    label: str = Field(description="stable machine key, e.g. 'domain_age_days'")
    value: Optional[str] = None
    confidence: float = Field(1.0, ge=0, le=1)
    source: str = Field(description="what produced it: 'whois', 'urlhaus', 'muril:v3'")
    detail: Optional[str] = None


class AgentResult(BaseModel):
    """The single shape every agent returns — ARCHITECTURE.md §3.

    Uniformity is the whole point. Because every agent returns this, the
    orchestrator can fan out without knowing what any agent does, the UI can
    render an agent panel generically, and the paper can compute per-agent
    success rates and inter-agent disagreement without a per-agent adapter.

    `features` is this agent's contribution to the ML feature vector in 4.1 —
    carried here rather than computed later so that the exact numbers the model
    saw are recorded alongside the findings that produced them.

    An agent that raises must still yield one of these, with `status=ERROR` and
    `error` set. A raising agent that propagates is a bug in the orchestrator,
    not a failed investigation.
    """

    agent: str = Field(description="registry name, e.g. 'url_investigation'")
    version: str = Field(description="pinned for reproducibility, e.g. '1.3.0'")
    status: AgentStatus
    confidence: float = Field(0.0, ge=0, le=1)
    findings: list[Finding] = Field(default_factory=list)
    features: dict[str, float] = Field(default_factory=dict)
    latency_ms: int = Field(0, ge=0)
    provenance: list[str] = Field(
        default_factory=list, description="data sources actually consulted"
    )
    error: Optional[str] = None


class TIRecord(BaseModel):
    """One threat-intelligence observation, with its paperwork attached.

    `malicious` is deliberately three-valued. A feed that is unreachable does
    not produce `False`; it produces `None` and a `degraded` tag. The single
    most damaging thing this system could do is invent an intelligence hit, so
    "we do not know" has to be representable.

    `cached` and `retrieved_at` exist because a demo that runs offline from a
    snapshot must say so rather than presenting a six-week-old record as live.
    """

    indicator: str
    indicator_type: str = Field(description="'url' | 'domain' | 'ip' | 'upi' | 'phone'")
    source: str = Field(description="feed name, e.g. 'urlhaus'")
    malicious: Optional[bool] = Field(
        None, description="None = the feed could not answer; never a guess"
    )
    confidence: float = Field(0.0, ge=0, le=1)
    observed_at: Optional[str] = Field(
        None, description="ISO-8601 UTC — when the feed saw it"
    )
    retrieved_at: Optional[str] = Field(
        None, description="ISO-8601 UTC — when we read it"
    )
    reference: Optional[str] = Field(None, description="resolvable link to the record")
    cached: bool = False


class GraphNeighbour(BaseModel):
    """An entity connected to this case in the knowledge graph."""

    key: str = Field(description="graph node id, e.g. 'upi:fraud@paytm'")
    kind: str = Field(description="'phone' | 'upi' | 'email' | 'domain' | ...")
    value: str
    relation: str = Field(description="how it connects, e.g. 'SHARED_UPI'")
    shared_cases: int = Field(0, ge=0)


class GraphContext(BaseModel):
    """What the knowledge graph already knew about this case's entities.

    This is the evidence no single artefact can carry: a UPI ID that looks
    unremarkable on its own but has appeared in four prior confirmed cases.

    `backend` records whether Neo4j or the NetworkX fallback answered, because
    a cluster score from the offline fallback covers less data and the report
    should not present the two as interchangeable.
    """

    prior_observations: int = Field(0, ge=0)
    prior_case_ids: list[str] = Field(default_factory=list)
    neighbours: list[GraphNeighbour] = Field(default_factory=list)
    cluster_id: Optional[str] = None
    cluster_risk: Optional[float] = Field(None, ge=0, le=100)
    centrality: Optional[float] = Field(None, ge=0)
    first_seen: Optional[str] = Field(None, description="ISO-8601 UTC")
    last_seen: Optional[str] = Field(None, description="ISO-8601 UTC")
    backend: str = Field("networkx", description="'neo4j' | 'networkx'")


class RetrievedChunk(BaseModel):
    """One passage retrieved from the knowledge base, with a real citation.

    `citation` must resolve to an actual chunk. Phase 3.5 gates on exactly
    that, because the failure mode here is not a bad answer — it is a
    confident answer citing a circular that does not exist.
    """

    chunk_id: str
    text: str
    source: str = Field(description="document identifier")
    citation: str = Field(description="human-resolvable reference")
    score: float = Field(0.0, ge=0)
    retriever: str = Field("dense", description="'dense' | 'bm25' | 'hybrid'")


class EvidenceFinding(BaseModel):
    """One ranked, human-readable item in the report.

    `id` exists so the explainability agent in 4.7 can be held to it: every
    sentence of generated prose must name the finding it rests on, and a
    grounding check rejects any claim that does not. Prose that cannot point
    at an id is a hallucination by definition.

    `contribution` is the SHAP value once 4.6/4.7 land, and stays None until
    then rather than being faked with a heuristic weight.
    """

    id: str
    title: str
    detail: str
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    contribution: Optional[float] = Field(
        None, description="SHAP contribution to the risk score, once measured"
    )
    agent: Optional[str] = Field(None, description="which agent produced it")
    sources: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """What the citizen should do, from a closed vocabulary."""

    action: RecommendedAction
    detail: str
    urgency: Severity = Severity.INFO
    sources: list[str] = Field(default_factory=list)


class TraceSpan(BaseModel):
    """One node execution. Debug tool, UI panel and paper table at once.

    `parent_span_id` and `depth` carry the fan-out shape: a URL agent that
    discovers a new domain spawns a bounded sub-investigation, and without the
    parent link the trace flattens into an unreadable list. `depth` is also
    the recursion bound the orchestrator enforces (default 2).

    `attempt` records retries. A node that succeeded on its second attempt is
    not the same as one that succeeded first time, and a latency percentile
    that silently averages the two is a measurement that lies.
    """

    span_id: str
    node: str = Field(description="graph node name")
    agent: Optional[str] = None
    version: Optional[str] = None
    t_start: float = Field(ge=0, description="seconds since investigation start")
    t_end: float = Field(ge=0)
    latency_ms: int = Field(0, ge=0)
    status: AgentStatus
    attempt: int = Field(1, ge=1)
    depth: int = Field(0, ge=0)
    parent_span_id: Optional[str] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------
# The investigation itself
# --------------------------------------------------------------------------


class InvestigationState(BaseModel):
    """The shared contract every agent reads and writes — ARCHITECTURE.md §3.

    Append-only in spirit: agents add to `agent_results`, `trace` and
    `degraded` rather than overwriting each other, which is what makes a
    parallel fan-out safe to merge and a crashed investigation safe to resume
    from a checkpoint.

    `risk_score`, `risk_level` and `confidence` are Optional and start None.
    An investigation that has not been scored yet must not read as 0/CALM —
    that is a false negative wearing a number, and it is the reason
    `StateFrame.threat` is Optional too. The UI renders None as "not yet",
    never as "safe".

    `risk_level` is a field rather than something the UI derives from
    `risk_score`, per the pure-renderer invariant: the live call path and the
    report path must band a 69.6 identically, and they will not if the
    threshold lives in React.
    """

    v: int = INVESTIGATION_CONTRACT_VERSION
    type: Literal["investigation"] = "investigation"

    # --- identity ---
    case_id: str
    org_id: str
    created_by: str
    created_at: str = Field(description="ISO-8601 UTC")
    mode: Literal["batch", "realtime"] = "batch"
    status: InvestigationStatus = InvestigationStatus.QUEUED
    completed_at: Optional[str] = Field(None, description="ISO-8601 UTC")

    # --- input ---
    inputs: list[EvidenceItem] = Field(default_factory=list)
    input_types: list[InputType] = Field(default_factory=list)

    # --- extraction ---
    extracted_text: list[ExtractedText] = Field(default_factory=list)
    entities: EntitySet = Field(default_factory=EntitySet)
    transcript: Optional[Transcript] = None

    # --- investigation ---
    agent_results: list[AgentResult] = Field(default_factory=list)
    threat_intel: list[TIRecord] = Field(default_factory=list)
    graph_context: Optional[GraphContext] = None
    rag_context: list[RetrievedChunk] = Field(default_factory=list)

    # --- judgement ---
    risk_features: dict[str, float] = Field(
        default_factory=dict, description="the ML model's exact input vector"
    )
    risk_score: Optional[float] = Field(None, ge=0, le=100)
    risk_level: Optional[ThreatLevel] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    classification: Optional[FraudCategory] = None
    evidence: list[EvidenceFinding] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)

    # --- operational ---
    degraded: list[str] = Field(default_factory=list)
    trace: list[TraceSpan] = Field(default_factory=list)


def utc_now_iso() -> str:
    """Timestamps on the wire are ISO-8601 UTC strings, not datetimes.

    Deliberate. Pydantic would happily carry `datetime`, but the moment a state
    is persisted as JSONB, replayed from a checkpoint, or compared in a test,
    the naive-vs-aware distinction that bit this project in 0.2 and again in
    0.6 comes back. A string that always ends in `Z` has one representation and
    survives every round trip identically.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --------------------------------------------------------------------------
# The lifecycle stream — what the API pushes while an investigation runs
# --------------------------------------------------------------------------


class InvestigationEventKind(str, Enum):
    """The five things the lifecycle API has to say while a case is running.

    Deliberately *not* a mirror of `EventKind`, which belongs to the live-call
    frame contract and names things that happen inside a scam ("payment
    attempted", "guardian alerted"). These name things that happen to an
    *investigation*, which is a different object with a different lifetime.

    There is no `node_started`. The graph tells us when a node finishes; a
    "started" event would be inferred from the plan rather than observed, and an
    inferred progress event is a fake timer wearing a node name — the exact
    thing task 1.9's acceptance criterion forbids. The client gets the whole
    node plan on `accepted` instead, so it can render "3 of 7" from two facts it
    was actually told.
    """

    ACCEPTED = "accepted"
    NODE_COMPLETE = "node_complete"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvestigationEvent(BaseModel):
    """One server-sent event on `GET /api/investigations/{id}/stream`.

    `seq` is the SSE `id:` field, monotonic from 1 within a single run. That is
    what makes reconnection exact rather than approximate: a client that saw
    event 4 sends `Last-Event-ID: 4` and is replayed 5 onward, so no event
    arrives twice and none is skipped. Keepalives go out as SSE comment lines,
    which carry no id by definition and therefore cannot be duplicated.

    `agent_results` carries only the results *this node produced*, not the
    accumulated list. A client that appends every event's results reconstructs
    `InvestigationState.agent_results` exactly, and one that reconnects mid-run
    does not double-count the earlier tiers.

    `degraded` is likewise the delta. An agent that fell back is visible in the
    frame it fell back in, which is what lets the UI show a degraded agent as
    degraded rather than hiding it behind a final summary.
    """

    v: int = INVESTIGATION_CONTRACT_VERSION
    type: Literal["investigation_event"] = "investigation_event"

    seq: int = Field(ge=1, description="monotonic within one run; the SSE event id")
    case_id: str
    kind: InvestigationEventKind
    at: str = Field(description="ISO-8601 UTC")
    status: InvestigationStatus

    node: Optional[str] = Field(None, description="graph node that just completed")
    plan: list[str] = Field(
        default_factory=list,
        description="every node this run will execute, in order — sent on `accepted`",
    )
    nodes_done: int = Field(0, ge=0)

    agent_results: list[AgentResult] = Field(
        default_factory=list, description="results produced by this node only"
    )
    degraded: list[str] = Field(
        default_factory=list, description="tags added by this node only"
    )
    error: Optional[str] = None
