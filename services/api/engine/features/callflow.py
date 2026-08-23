"""
A. Call-flow sequence features.

The spec's core claim: "Rather than relying on keywords, the classifier learns
these sequential behavioural patterns." This module produces the sequence
representation that claim depends on.

The canonical arc, and why the observed one is collapsed
--------------------------------------------------------
A scammer spends several consecutive turns inside one stage. A raw turn-by-turn
sequence is therefore ~85% self-transitions (measured in this project's own
corpus — see `ml/build_dataset.py::fit_transitions`), and any pattern learned
over it is dominated by "the stage stayed the same". Collapsing consecutive
repeats turns the sequence into what it actually needs to be: an ordered record
of *transitions*, which is where the scam structure lives.

What this buys over a single-turn classifier
--------------------------------------------
A lone "aapka account number bataiye" is ambiguous — legitimate service calls
ask that. The same sentence arriving after AUTHORITY_CLAIM → FEAR_INDUCTION →
ISOLATION is not ambiguous at all. Arc adherence is what makes that difference
computable rather than intuitive.

Regressions are tracked because they are diagnostic in both directions. A
scammer loops back to fear after resistance — that is a documented tactic and
the corpus generator explicitly produces it. A benign call does not oscillate
between authority and payment stages at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Canonical Digital Arrest arc. BENIGN is deliberately absent — it is not a
#: position on the arc, it is the absence of one, and giving it an index would
#: make "progression" meaningless for legitimate calls.
CANONICAL_ARC = [
    "GREETING",
    "AUTHORITY_CLAIM",
    "FEAR_INDUCTION",
    "ISOLATION",
    "VERIFICATION_DEMAND",
    "PAYMENT_SETUP",
    "PAYMENT_EXECUTION",
]

_ARC_INDEX = {stage: i for i, stage in enumerate(CANONICAL_ARC)}

#: Spec-to-implementation stage mapping. The specification names eight steps
#: (Greeting, Authority Introduction, Criminal Allegation, Fear Escalation,
#: Isolation, Identity Verification, Payment Demand, Exit). This build keeps
#: the seven-stage arc plus BENIGN that the corpus is labelled and trained on.
#:
#: Two deliberate reconciliations:
#:   - "Criminal Allegation" and "Fear Escalation" are one label here
#:     (FEAR_INDUCTION). They are the same speech act at different intensities,
#:     and splitting a class that already has only 85 training examples would
#:     make both halves unlearnable.
#:   - "Exit" is not a stage. It is the end of the call, and it is already
#:     represented as the CALL_ENDED event, which carries the outcome. A stage
#:     with no utterances to classify cannot be predicted from an utterance.
SPEC_STAGE_NAMES = {
    "GREETING": "Greeting",
    "AUTHORITY_CLAIM": "Authority Introduction",
    "FEAR_INDUCTION": "Criminal Allegation / Fear Escalation",
    "ISOLATION": "Isolation",
    "VERIFICATION_DEMAND": "Identity Verification",
    "PAYMENT_SETUP": "Payment Demand",
    "PAYMENT_EXECUTION": "Payment Execution",
    "BENIGN": "Benign (no scam arc)",
}


@dataclass
class CallFlowFeatures:
    sequence: list[str] = field(default_factory=list)
    arc_adherence: float = 0.0
    progression: float = 0.0
    stages_seen: int = 0
    regressions: int = 0
    #: Longest run of strictly forward moves along the arc. A scam that is
    #: working looks like a long clean ascent.
    longest_advance: int = 0
    #: True once the call has entered the half of the arc where money is the
    #: explicit subject. Used as a hard gate by the alert engine.
    reached_payment_half: bool = False
    #: Fixed-width vector for the sequence model. Order is stable and is part
    #: of the trained model's input contract — see ml/rssie/features.py.
    vector: list[float] = field(default_factory=list)


class CallFlowTracker:
    """Accumulates the collapsed stage sequence across a call."""

    def __init__(self) -> None:
        self.sequence: list[str] = []

    def observe(self, stage: str) -> None:
        """Record a stage. Consecutive repeats collapse into one entry."""
        if not stage:
            return
        if self.sequence and self.sequence[-1] == stage:
            return
        self.sequence.append(stage)

    def snapshot(self) -> CallFlowFeatures:
        return compute(self.sequence)


def compute(sequence: list[str]) -> CallFlowFeatures:
    """Derive flow features from a collapsed stage sequence."""
    scam_steps = [s for s in sequence if s in _ARC_INDEX]

    if not scam_steps:
        # No scam stage ever fired. Adherence is 0 rather than undefined, and
        # that is correct: a benign call has no arc to adhere to.
        return CallFlowFeatures(
            sequence=list(sequence),
            vector=_vector(0.0, 0.0, 0, 0, 0, False),
        )

    indices = [_ARC_INDEX[s] for s in scam_steps]

    # Adherence = fraction of transitions that move forward along the arc.
    # Measured over transitions rather than positions so a call that starts
    # mid-arc (common — many scams skip the greeting) is not penalised for
    # where it began, only for where it went.
    forward = sum(1 for a, b in zip(indices, indices[1:]) if b > a)
    regressions = sum(1 for a, b in zip(indices, indices[1:]) if b < a)
    transitions = len(indices) - 1
    adherence = forward / transitions if transitions else (1.0 if indices else 0.0)

    # Progression = how deep into the arc the call has reached. Uses the max,
    # not the last: a call that reached PAYMENT_SETUP and then looped back to
    # fear has still reached payment territory, and the risk does not reset.
    progression = max(indices) / (len(CANONICAL_ARC) - 1)

    longest = current = 0
    for a, b in zip(indices, indices[1:]):
        current = current + 1 if b > a else 0
        longest = max(longest, current)

    reached_payment_half = max(indices) >= _ARC_INDEX["VERIFICATION_DEMAND"]

    return CallFlowFeatures(
        sequence=list(sequence),
        arc_adherence=round(adherence, 3),
        progression=round(progression, 3),
        stages_seen=len(set(scam_steps)),
        regressions=regressions,
        longest_advance=longest,
        reached_payment_half=reached_payment_half,
        vector=_vector(adherence, progression, len(set(scam_steps)), regressions,
                       longest, reached_payment_half),
    )


def _vector(
    adherence: float,
    progression: float,
    stages_seen: int,
    regressions: int,
    longest: int,
    reached_payment_half: bool,
) -> list[float]:
    """Fixed 6-dim flow vector. Normalised so every element is 0-1 — the
    sequence head concatenates this with text embeddings, and an unnormalised
    count would dominate them purely by magnitude."""
    return [
        round(adherence, 4),
        round(progression, 4),
        round(min(1.0, stages_seen / len(CANONICAL_ARC)), 4),
        round(min(1.0, regressions / 4.0), 4),
        round(min(1.0, longest / len(CANONICAL_ARC)), 4),
        1.0 if reached_payment_half else 0.0,
    ]


def transfer_risk_from_flow(features: CallFlowFeatures) -> float:
    """Flow-only estimate of how close this call is to money moving.

    Deliberately not the final answer — `engine/twin.py` owns the calibrated
    ETA, fitted on real transition statistics. This is the structural component
    of that estimate, and it exists so transfer risk has a value even before
    the twin has enough context to forecast.
    """
    if not features.sequence:
        return 0.0
    risk = features.progression * 0.6 + features.arc_adherence * 0.2
    if features.reached_payment_half:
        risk += 0.2
    return round(min(1.0, risk), 3)
