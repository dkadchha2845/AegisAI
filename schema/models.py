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
