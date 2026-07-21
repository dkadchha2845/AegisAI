"""
Live session — the state machine that turns utterances into StateFrames.

One `Session` per call. It owns every stateful component (the manipulation
accumulator, the coercion tracker, the trust passport, the twin's pending
prediction) and emits contract messages: a complete `StateFrame` snapshot on
every tick, plus discrete `Event`s at the edges.

The snapshot/edge split is load-bearing rather than stylistic. Frames are
idempotent, so a client that missed ten of them is fully correct after the
next one — that is what makes the demo survive a dropped socket on stage.
Edges are emitted exactly once by the side that knows the truth, so an
animation never fires twice or not at all because two frames arrived out of
order.

Nothing in here derives a value the frontend could also derive. If the UI
needs a number, it becomes a field on the frame; the alternative is the same
logic drifting apart in two languages.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..rag.coach import get_coach
from ..rag.store import get_kb
from .classifier import load_classifier
from .coercion import CoercionTracker
from .passport import TrustPassport
from .scripts import get_script_matcher
from .spoofing import analyze_number
from .threat import ManipulationAccumulator, fuse
from .twin import DigitalTwin

CONTRACT_VERSION = 1

#: Threat score at which the guardian is alerted. Chosen to sit at the bottom
#: of HIGH: alerting inside ELEVATED trains people to ignore the alert, and
#: waiting for CRITICAL means alerting after the money has moved.
GUARDIAN_THRESHOLD = 70.0

#: Payments attempted at or above this score are held rather than executed.
#: The hold is reversible and short; the transfer is not.
PAYMENT_HOLD_THRESHOLD = 55.0


@dataclass
class Utterance:
    id: str
    speaker: str
    text: str
    t0: float
    t1: float
    stage: str
    confidence: float
    victim_state: str


@dataclass
class Narration:
    """Plain-language account of what the system is doing and why.

    This is a contract field rather than frontend copy for the same reason
    every other number is: the explanation has to agree with the score it is
    explaining, and two implementations of "what's happening" would eventually
    disagree. It is also the difference between a dashboard someone watches
    and one they understand.
    """

    headline: str
    detail: str
    sources: list[str] = field(default_factory=list)


class Session:
    def __init__(self, session_id: str | None = None, caller_number: str | None = None):
        self.id = session_id or f"s_{uuid.uuid4().hex[:10]}"
        self.seq = 0
        self.started_at = time.time()
        self.caller_number = caller_number
        self.status = "active"

        self.classifier = load_classifier()
        self.twin = DigitalTwin()
        self.manipulation = ManipulationAccumulator()
        self.coercion = CoercionTracker()
        self.passport = TrustPassport()
        self.script_matcher = get_script_matcher()
        self.script_similarity = 0.0
        self.script_label: str | None = None

        self.utterances: list[Utterance] = []
        self.partial: str | None = None
        self.partial_speaker: str | None = None

        # Caller-number intelligence. Computed once up front from the number
        # alone, then refined in _recompute as the passport resolves who the
        # caller claims to be — the sharpest check (authority vs personal
        # mobile) needs both halves.
        self.number_intel = analyze_number(caller_number)

        self.stage = "GREETING"
        self.stage_confidence = 0.0
        self.stage_since = 0.0
        self.stage_distribution: dict[str, float] = {}
        self.threat_score = 0.0
        self.threat_level = "CALM"
        self.threat_drivers: list[dict] = []
        #: Highest threat reached this call. The live meter ratchets and can ease
        #: back; an evidence report needs the peak, not the reading at export time.
        self.peak_threat = 0.0
        self.peak_stage = "GREETING"
        self.coercion_index = 0.0
        self.coercion_trend = "flat"
        self.coercion_history: list[float] = []
        self.coercion_features: dict[str, float] = {}
        self.victim_state = "UNKNOWN"
        self.last_forecast = None
        self.forecast_correct: bool | None = None
        self.narration = Narration(
            "Listening.", "No caller audio classified yet.", []
        )

        self.guardian_state = "IDLE"
        self.guardian_name: str | None = None
        self.guardian_alerted_at: float | None = None
        self.guardian_acked_at: float | None = None

        self.payment_state = "NONE"
        self.payment_amount: float | None = None
        self.payment_payee: str | None = None
        self.payment_held_reason: str | None = None
        self.payment_held_at: float | None = None

        self._coach_escalation: dict[str, int] = {}
        self.coach = None
        self._events: list[dict] = []
        self._last_tick = 0.0
        self._degraded_static: list[str] = list(get_kb().degraded)
        if self.classifier.backend != "muril":
            self._degraded_static.append("clf:lexical_fallback")
        self._degraded_static += self.twin.degraded

    # -- clock -------------------------------------------------------------

    @property
    def t(self) -> float:
        return round(time.time() - self.started_at, 2)

    # -- ingestion ---------------------------------------------------------

    def set_partial(self, text: str, speaker: str = "CALLER") -> None:
        """In-flight ASR. Rendered dimmed and never scored — classifying a
        half-finished sentence produces a label that flips as the rest of it
        arrives, and a stage chip that flickers is worse than a late one."""
        self.partial = text or None
        self.partial_speaker = speaker if text else None

    def ingest(self, text: str, speaker: str = "CALLER", duration_s: float = 3.0) -> None:
        text = text.strip()
        if not text:
            return
        self.partial = None
        self.partial_speaker = None
        now = self.t
        previous_stage = self.stage

        if speaker == "CALLER":
            history = [u.text for u in self.utterances[-2:]]
            pred = self.classifier.predict(text, history)
            self.stage_distribution = {
                k: round(v, 4) for k, v in sorted(pred.distribution.items(), key=lambda kv: -kv[1])
            }
            self.stage_confidence = pred.confidence
            if pred.label != self.stage:
                # Score the twin's standing prediction before overwriting it.
                self.forecast_correct = self.twin.score_transition(self.stage, pred.label)
                self._emit("STAGE_CHANGED", {"from": self.stage, "to": pred.label})
                if self.forecast_correct:
                    self._emit(
                        "FORECAST_HIT",
                        {"stage": pred.label, "accuracy": self.twin.accuracy},
                    )
                self.stage = pred.label
                self.stage_since = now
            self.manipulation.observe(pred.label, pred.confidence)
            self.passport.observe(text, speaker)
            # Script similarity. Keep the running peak — a line 94% similar to a
            # known script is a fact about the call that stays true when the
            # caller later chats about the weather.
            m = self.script_matcher.match(text)
            if m.similarity > self.script_similarity:
                self.script_similarity = m.similarity
                self.script_label = m.label
        else:
            out = self.coercion.observe(text, duration_s=duration_s)
            self.coercion_index = out.index
            self.coercion_trend = out.trend
            self.coercion_history = out.history
            self.coercion_features = out.features
            self.victim_state = out.victim_state
            self.manipulation.observe_victim(out.victim_state)

        self.utterances.append(
            Utterance(
                id=f"u{len(self.utterances):04d}",
                speaker=speaker,
                text=text,
                t0=round(max(0.0, now - duration_s), 2),
                t1=now,
                stage=self.stage if speaker == "CALLER" else "BENIGN",
                confidence=round(self.stage_confidence, 3) if speaker == "CALLER" else 0.0,
                victim_state=self.victim_state,
            )
        )
        self._recompute(previous_stage)

    # -- scoring -----------------------------------------------------------

    def _recompute(self, previous_stage: str) -> None:
        now = self.t
        dt = max(0.0, now - self._last_tick)
        self._last_tick = now
        passport = self.passport.snapshot()

        # Refine number intelligence now that the passport may have resolved a
        # claimed identity — the Caller-ID-vs-authority check needs it.
        self.number_intel = analyze_number(
            self.caller_number,
            claimed_identity=self.passport.claimed_identity,
        )

        previous_level = self.threat_level
        fusion = fuse(
            stage=self.stage,
            stage_confidence=self.stage_confidence,
            manipulation=self.manipulation,
            coercion_index=self.coercion_index,
            trust_pct=passport.final_trust_pct if passport.checks else None,
            spoofing_risk=self.number_intel.risk if self.caller_number else None,
            script_similarity=self.script_similarity,
            script_label=self.script_label,
            previous_score=self.threat_score,
            dt_s=dt,
        )
        self.threat_score = fusion.score
        self.threat_level = fusion.level
        self.threat_drivers = [asdict(d) for d in fusion.drivers]
        if fusion.score > self.peak_threat:
            self.peak_threat = fusion.score
            self.peak_stage = self.stage

        if fusion.level != previous_level:
            self._emit(
                "THRESHOLD_CROSSED",
                {"level": fusion.level, "from": previous_level, "score": fusion.score},
            )

        self.last_forecast = self.twin.forecast(self.stage, since_s=now - self.stage_since)

        # Coach. Escalates within a stage so a line that visibly failed is not
        # repeated verbatim.
        escalation = self._coach_escalation.get(self.stage, 0)
        coach = get_coach().suggest(
            self.stage, escalation=escalation, victim_state=self.victim_state
        )
        if coach is not None:
            was_urgent = self.coach is not None and self.coach.urgency == "urgent"
            self.coach = coach
            self._coach_escalation[self.stage] = escalation + 1
            if coach.urgency == "urgent" and not was_urgent:
                self._emit("COACH_URGENT", {"line": coach.line, "tactic": coach.tactic})

        self._update_narration(previous_stage)

        # Guardian escalation. Fires once, on the crossing.
        if self.threat_score >= GUARDIAN_THRESHOLD and self.guardian_state == "IDLE":
            self.guardian_state = "ALERTING"
            self.guardian_alerted_at = now
            self._emit(
                "GUARDIAN_ALERTED",
                {"score": self.threat_score, "stage": self.stage, "name": self.guardian_name},
            )

    def _update_narration(self, previous_stage: str) -> None:
        """Say what just happened, in the words a person would use."""
        kb = get_kb()
        hits = kb.search(self.stage.replace("_", " "), k=1, tags=[f"stage:{self.stage}"])
        sources = [h.chunk.source for h in hits]

        stage_label = self.stage.replace("_", " ").lower()
        if self.stage != previous_stage:
            headline = f"Caller moved to {stage_label}."
        else:
            headline = f"Caller is still in {stage_label}."

        parts = [
            f"Threat is {self.threat_score:.0f}/100 ({self.threat_level})."
        ]
        if self.threat_drivers:
            top = self.threat_drivers[0]
            parts.append(f"Biggest contributor: {top['label'].lower()} — {top['detail']}.")
        if self.last_forecast is not None:
            eta = self.last_forecast.eta_to_payment_s
            nxt = self.last_forecast.next_stage.replace("_", " ").lower()
            parts.append(
                f"The twin expects {nxt} next ({self.last_forecast.probability:.0%})."
            )
            if eta is not None and self.stage != "BENIGN":
                parts.append(f"If nobody intervenes, money moves in about {eta:.0f}s.")
        if self.guardian_state == "ALERTING":
            parts.append("The guardian has been alerted and is waiting to acknowledge.")
        if self.payment_state == "HELD":
            parts.append("A payment is currently held pending guardian review.")

        self.narration = Narration(headline, " ".join(parts), sources)

    # -- guardian & payment actions ---------------------------------------

    def guardian_ack(self, name: str | None = None) -> None:
        if self.guardian_state in {"IDLE", "ACKNOWLEDGED"} and name:
            self.guardian_name = name
        self.guardian_state = "ACKNOWLEDGED"
        self.guardian_acked_at = self.t
        self._emit("GUARDIAN_ACKNOWLEDGED", {"name": self.guardian_name})
        self._update_narration(self.stage)

    def attempt_payment(self, amount: float, payee: str | None = None) -> dict:
        """The circuit breaker. A payment attempted during a call the system
        believes is coercive is held, not executed — the hold is reversible in
        seconds and the transfer is not, so the asymmetry decides it."""
        self.payment_amount = amount
        self.payment_payee = payee
        self._emit("PAYMENT_ATTEMPTED", {"amount_inr": amount, "payee": payee})

        if self.threat_score >= PAYMENT_HOLD_THRESHOLD:
            self.payment_state = "HELD"
            self.payment_held_at = self.t
            self.payment_held_reason = (
                f"Threat {self.threat_score:.0f}/100 during {self.stage.replace('_', ' ').lower()}"
            )
            self._emit(
                "PAYMENT_HELD",
                {"amount_inr": amount, "payee": payee, "reason": self.payment_held_reason},
            )
        else:
            self.payment_state = "PENDING"
        self._update_narration(self.stage)
        return {"state": self.payment_state, "reason": self.payment_held_reason}

    def cancel_payment(self) -> None:
        self.payment_state = "CANCELLED"
        self._emit("PAYMENT_CANCELLED", {"amount_inr": self.payment_amount})
        self._update_narration(self.stage)

    def approve_payment(self) -> None:
        """Explicit guardian override. Deliberately available: a system that
        cannot be overridden by the account holder's own trusted contact is
        one they will route around entirely."""
        self.payment_state = "APPROVED"
        self._update_narration(self.stage)

    def end(self) -> None:
        self.status = "ended"
        self._emit(
            "CALL_ENDED",
            {
                "duration_s": self.t,
                "peak_threat": self.threat_score,
                "twin_accuracy": self.twin.accuracy,
            },
        )

    # -- contract emission -------------------------------------------------

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        self.seq += 1
        self._events.append(
            {
                "v": CONTRACT_VERSION,
                "type": "event",
                "session_id": self.id,
                "seq": self.seq,
                "t": self.t,
                "kind": kind,
                "payload": payload,
            }
        )

    def drain_events(self) -> list[dict]:
        events, self._events = self._events, []
        return events

    def frame(self) -> dict:
        """A complete, idempotent snapshot. Safe to drop, replay, or reorder."""
        self.seq += 1
        passport = self.passport.snapshot()
        degraded = list(self._degraded_static)
        if "coercion:text_only" not in degraded and not self.coercion_features.get("pause_ratio"):
            degraded.append("coercion:text_only")

        return {
            "v": CONTRACT_VERSION,
            "type": "state",
            "session_id": self.id,
            "seq": self.seq,
            "t": self.t,
            "call": {
                "status": self.status,
                "duration_s": self.t,
                "caller_number": self.caller_number,
                "started_at": None,
            },
            "transcript": {
                "final": [asdict(u) for u in self.utterances],
                "partial": self.partial,
                "partial_speaker": self.partial_speaker,
            },
            "stage": {
                "current": self.stage,
                "confidence": round(self.stage_confidence, 3),
                "since_s": round(self.t - self.stage_since, 2),
                "distribution": self.stage_distribution,
            },
            "coercion": {
                "index": self.coercion_index,
                "trend": self.coercion_trend,
                "history": self.coercion_history,
                "features": self.coercion_features,
            },
            "threat": {
                "score": self.threat_score,
                "level": self.threat_level,
                "drivers": self.threat_drivers,
            },
            "manipulation_map": self.manipulation.as_dict(),
            "forecast": (
                {
                    **asdict(self.last_forecast),
                    "last_prediction_correct": self.forecast_correct,
                }
                if self.last_forecast
                else None
            ),
            "trust_passport": asdict(passport),
            "number_intel": asdict(self.number_intel),
            "coach": asdict(self.coach) if self.coach else None,
            "narration": asdict(self.narration),
            "guardian": {
                "state": self.guardian_state,
                "name": self.guardian_name,
                "alerted_at_s": self.guardian_alerted_at,
                "acknowledged_at_s": self.guardian_acked_at,
            },
            "payment": {
                "state": self.payment_state,
                "amount_inr": self.payment_amount,
                "payee": self.payment_payee,
                "held_reason": self.payment_held_reason,
                "held_at_s": self.payment_held_at,
            },
            "degraded": degraded,
        }


class SessionRegistry:
    """In-process session store. Deliberately not Redis — one demo machine,
    one process, and a dependency that can fail on stage buys nothing."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, caller_number: str | None = None) -> Session:
        session = Session(caller_number=caller_number)
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def drop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def all(self) -> list[Session]:
        return list(self._sessions.values())


registry = SessionRegistry()
