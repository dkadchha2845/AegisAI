"""
Threat fusion — where the number on the meter comes from.

The score is a weighted sum of four independent signals, and the weights are
here in one readable table rather than scattered through the pipeline. Two
properties matter more than the exact numbers:

1. **Every point is attributable.** The function returns the drivers that
   produced the score, each with its own contribution. A meter reading 91 with
   no explanation is a demo; 91 *because* of three named signals is a product.

2. **The score ratchets.** Threat decays slowly and rises fast. A scammer who
   spends thirty seconds being pleasant after inducing terror has not made the
   call safer, and a meter that drifts back to CALM during that lull would
   teach the user to ignore it. `fuse()` therefore takes the previous score and
   never lets the result fall more than DECAY_PER_S per second.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from .classifier import threat_weight

# The four conversational signals sum to 1.0 at full saturation.
W_STAGE = 0.40          # what the caller is doing right now
W_TACTIC = 0.25         # cumulative manipulation pressure over the call
W_COERCION = 0.20       # victim stress from the audio side
W_TRUST = 0.15          # failed identity checks from the Trust Passport

#: Number spoofing is corroborating *metadata*, not part of the conversation,
#: so it rides as a bounded escalator on top of the four-signal sum rather than
#: stealing weight from it: a call that reads 60 on content alone should read
#: higher, not have its content signals diluted, when the caller ID is also
#: forged. Capped so metadata can never manufacture a CRITICAL on its own —
#: a spoofed number with a silent, benign conversation tops out in HIGH.
W_SPOOF = 0.18

#: Script-template similarity — how close the caller's line is to a known scam
#: script. Also a bounded escalator, and gated by SCRIPT_MIN so ordinary
#: conversation that happens to share common words never fires it. A real bank
#: call does not paraphrase the CBI arrest script.
W_SCRIPT = 0.15
SCRIPT_MIN = 0.45

#: Threat may not fall faster than this. Chosen so a full CRITICAL -> CALM
#: takes ~40s of sustained benign conversation, which is roughly how long a
#: real de-escalation takes.
DECAY_PER_S = 2.5


@dataclass
class ThreatDriverOut:
    label: str
    contribution: float
    detail: str


@dataclass
class ManipulationAccumulator:
    """Cumulative tactic pressure. Rises with evidence, never falls — the call
    does not become less manipulative because the manipulation stopped."""

    authority: float = 0.0
    fear: float = 0.0
    isolation: float = 0.0
    urgency: float = 0.0
    compliance: float = 0.0

    #: Stage -> which tactic bar it charges, and by how much per utterance.
    _CHARGE: ClassVar[dict[str, tuple[str, float]]] = {
        "AUTHORITY_CLAIM": ("authority", 0.34),
        "FEAR_INDUCTION": ("fear", 0.30),
        "ISOLATION": ("isolation", 0.38),
        "VERIFICATION_DEMAND": ("urgency", 0.22),
        "PAYMENT_SETUP": ("urgency", 0.26),
        "PAYMENT_EXECUTION": ("compliance", 0.40),
    }

    def observe(self, stage: str, confidence: float) -> None:
        entry = self._CHARGE.get(stage)
        if entry is None:
            return
        field_name, amount = entry
        current = getattr(self, field_name)
        setattr(self, field_name, min(1.0, current + amount * confidence))

    def observe_victim(self, victim_state: str) -> None:
        """Victim compliance is evidence of tactic success, not tactic use."""
        if victim_state == "COMPLIANT":
            self.compliance = min(1.0, self.compliance + 0.15)
        elif victim_state == "PANICKED":
            self.fear = min(1.0, self.fear + 0.10)

    @property
    def pressure(self) -> float:
        """Mean of the five bars, 0-1."""
        return (
            self.authority + self.fear + self.isolation
            + self.urgency + self.compliance
        ) / 5.0

    def as_dict(self) -> dict[str, float]:
        return {
            "authority": round(self.authority, 3),
            "fear": round(self.fear, 3),
            "isolation": round(self.isolation, 3),
            "urgency": round(self.urgency, 3),
            "compliance": round(self.compliance, 3),
        }


@dataclass
class FusionResult:
    score: float
    level: str
    drivers: list[ThreatDriverOut] = field(default_factory=list)


def level_of(score: float) -> str:
    """Mirrors threat_level() in schema/models.py. Kept in lockstep by
    schema/check_contract.py, which fails the build if the bands drift."""
    if score >= 90:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "ELEVATED"
    if score >= 25:
        return "WATCH"
    return "CALM"


def fuse(
    *,
    stage: str,
    stage_confidence: float,
    manipulation: ManipulationAccumulator,
    coercion_index: float,
    trust_pct: float | None,
    spoofing_risk: float | None = None,
    script_similarity: float | None = None,
    script_label: str | None = None,
    previous_score: float = 0.0,
    dt_s: float = 0.25,
) -> FusionResult:
    """Combine the conversational signals — plus optional number-spoofing
    metadata — into a 0-100 score plus its explanation."""
    drivers: list[ThreatDriverOut] = []

    # 1. Current stage, discounted by how sure the classifier is. An uncertain
    #    ISOLATION call should not slam the meter to 90.
    stage_component = threat_weight(stage) * stage_confidence * W_STAGE * 100
    if stage_component > 1:
        drivers.append(
            ThreatDriverOut(
                label=f"Stage: {stage.replace('_', ' ').title()}",
                contribution=round(stage_component / 100, 3),
                detail=f"classifier {stage_confidence:.0%} confident",
            )
        )

    # 2. Cumulative tactic pressure.
    tactic_component = manipulation.pressure * W_TACTIC * 100
    if tactic_component > 1:
        top = max(
            manipulation.as_dict().items(), key=lambda kv: kv[1]
        )
        drivers.append(
            ThreatDriverOut(
                label="Manipulation pressure",
                contribution=round(tactic_component / 100, 3),
                detail=f"strongest tactic: {top[0]} at {top[1]:.0%}",
            )
        )

    # 3. Victim stress.
    coercion_component = (coercion_index / 100.0) * W_COERCION * 100
    if coercion_component > 1:
        drivers.append(
            ThreatDriverOut(
                label="Victim stress",
                contribution=round(coercion_component / 100, 3),
                detail=f"coercion index {coercion_index:.0f}/100",
            )
        )

    # 4. Identity checks. Only counts once the passport has actually run —
    #    an unrun check is not a failed check.
    trust_component = 0.0
    if trust_pct is not None:
        trust_component = (1.0 - trust_pct / 100.0) * W_TRUST * 100
        if trust_component > 1:
            drivers.append(
                ThreatDriverOut(
                    label="Identity unverified",
                    contribution=round(trust_component / 100, 3),
                    detail=f"trust passport at {trust_pct:.0f}%",
                )
            )

    # 5. Number spoofing — corroborating metadata, added on top. Only counts
    #    when a number was actually analysed; an absent number is not a clean
    #    number, so `None` contributes nothing rather than reading as safe.
    spoof_component = 0.0
    if spoofing_risk is not None:
        spoof_component = (spoofing_risk / 100.0) * W_SPOOF * 100
        if spoof_component > 1:
            drivers.append(
                ThreatDriverOut(
                    label="Number spoofing",
                    contribution=round(spoof_component / 100, 3),
                    detail=f"caller-number risk {spoofing_risk:.0f}/100",
                )
            )

    # 6. Script-template similarity. Gated: below SCRIPT_MIN it contributes
    #    nothing, so shared-vocabulary coincidence in a benign call is not a
    #    signal — only a genuine paraphrase of a known script is.
    script_component = 0.0
    if script_similarity is not None and script_similarity >= SCRIPT_MIN:
        script_component = script_similarity * W_SCRIPT * 100
        if script_component > 1:
            label = (script_label or "scam").replace("_", " ").lower()
            drivers.append(
                ThreatDriverOut(
                    label="Script match",
                    contribution=round(script_component / 100, 3),
                    detail=f"{script_similarity:.0%} similar to a known {label} script",
                )
            )

    raw = (
        stage_component + tactic_component + coercion_component
        + trust_component + spoof_component + script_component
    )
    score = max(0.0, min(100.0, raw))

    # Ratchet: fast up, slow down.
    floor = previous_score - DECAY_PER_S * dt_s
    if score < floor:
        score = floor

    drivers.sort(key=lambda d: d.contribution, reverse=True)
    return FusionResult(score=round(score, 1), level=level_of(score), drivers=drivers[:4])
