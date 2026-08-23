"""
G. Emotional features.

The spec's eight states: Calm, Curious, Confused, Fearful, Panicked, Trusting,
Resistant, Compliant. And its framing, which this module takes literally:

    "Emotion is supportive intelligence, not the main classifier."

So this file produces no scam probability and never will. It answers one
question — how well is the manipulation working — and hands that to fusion as
one signal among several.

Why this is not just `coercion.py` with more labels
---------------------------------------------------
`engine/coercion.py` produces a single 0-100 stress index and a 7-state
`VictimState`. It stays exactly as it is; nothing here replaces it. What this
adds is the two states that index cannot represent, and they are the two that
matter most for measuring manipulation:

  CURIOUS  — engaged but still evaluating. Low stress, low risk.
  TRUSTING — engaged and no longer evaluating. Low stress, HIGH risk.

Both read as "calm" on a stress index. They are opposite conditions. A victim
who has accepted the caller's authority is unafraid precisely *because* the
manipulation succeeded, and a system that scores calm as safe will report its
lowest risk at the moment the transfer is agreed.

`manipulation_effectiveness` is therefore not stress. It is how far the victim
has moved from evaluating toward accepting, which is what fusion needs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar

# --- Per-state lexical evidence --------------------------------------------
# Weighted because these are not equally diagnostic: "arrest ho jayega?" is a
# strong fear marker, a bare "please" is weak.

_CUES: dict[str, list[tuple[str, float]]] = {
    "CALM": [
        (r"\b(theek hai|achha|ok|okay|samajh gaya)\b", 0.5),
        (r"\b(boliye|bataiye kya baat hai|kaise|haan ji)\b", 0.4),
    ],
    "CURIOUS": [
        (r"\b(kaise|kyun|kya matlab|what do you mean|kaun se)\b.*\?", 0.8),
        (r"\b(aap kaun|which department|kis department|konsa office)\b", 0.9),
        (r"\b(proof|documents?|likhit|written|email (bhej|send))\b", 0.85),
        (r"\b(kaise pata|how do you know|verify kaise)\b", 0.9),
    ],
    "CONFUSED": [
        (r"\b(samajh nahi|samjha nahi|pata nahi|nahi pata)\b", 0.9),
        (r"\b(kya\?|matlab\?|kaisa case|kaun sa parcel)\b", 0.7),
        (r"\b(maine to kuch nahi|i didn'?t|maine koi)\b", 0.8),
        (r"\b(phir se|dobara|repeat|again)\b", 0.5),
        (r"\.\.\.|…", 0.3),
    ],
    "FEARFUL": [
        (r"\b(dar lag|darr|ghabra|scared|afraid)\w*", 1.0),
        (r"\b(arrest|jail|police)\b.{0,25}\?", 0.85),
        (r"\b(mera kya hoga|kya hoga|what will happen)\b", 0.9),
        (r"\b(pareshan|tension|worried|nervous)\b", 0.8),
        (r"\b(sach mein|really)\b.{0,20}\b(arrest|case|warrant)\b", 0.7),
    ],
    "PANICKED": [
        (r"\b(bhagwan|god|hey ram|oh no)\b", 0.9),
        (r"\b(kya karu|kya karna hoga|what should i do|help)\b", 1.0),
        (r"\b(please|pleej)\b.{0,20}\b(save|bachaiye|madad|help)\b", 1.0),
        (r"\b(dil|heart|saans|chakkar)\b.{0,15}\b(ghabra|tez|nahi)\w*", 0.95),
        (r"\b(mera career|meri naukri|meri izzat|my life)\b", 0.85),
        (r"!{2,}", 0.4),
    ],
    "TRUSTING": [
        # The dangerous quiet. The victim has accepted the frame and is now
        # cooperating with what they believe is a legitimate process.
        (r"\b(ji sir|yes sir|bilkul sir|jo aap kahen)\b", 0.7),
        (r"\b(aap sahi keh rahe|you'?re right|aapki baat sahi)\b", 0.95),
        (r"\b(thank you|dhanyavaad|shukriya)\b.{0,25}\b(help|madad|batane)\w*", 0.9),
        (r"\b(main aap par|i trust|bharosa)\b", 1.0),
        (r"\b(accha hua aapne bataya|good thing you called)\b", 0.95),
    ],
    "RESISTANT": [
        (r"\b(main khud|myself)\b.{0,25}\b(check|verify|call|dekh)\w*", 1.0),
        (r"\b(nahi)\b.{0,20}\b(dunga|dungi|bataunga|bataungi|karunga)\b", 1.0),
        (r"\b(bank|branch|police station|1930)\b.{0,20}\b(jaunga|jaungi|call kar)\w*", 1.0),
        (r"\b(ye fraud|ye scam|jhooth|fake|believe nahi)\b", 1.0),
        (r"\b(bete|beti|husband|wife|family)\b.{0,20}\b(baat|pooch)\w*", 0.9),
        (r"\b(call back|baad mein|later)\b", 0.6),
    ],
    "COMPLIANT": [
        (r"\bkar (raha|rahi|deta|deti) hoon\b", 1.0),
        (r"\b(bhej|kar) (diya|diya hai)\b", 1.0),
        (r"\b(ho gaya|done|complete|successful)\b", 0.95),
        (r"\b(app khul|likh raha|note kar raha|daal diya)\w*", 0.95),
        (r"\b(theek hai)\b.{0,20}\b(bhej|kar|de)\w*", 0.8),
        (r"\b(aadhaar|otp|account|pin)\b.{0,15}\b(hai|number is)\b.{0,5}\d", 1.0),
    ],
}

_COMPILED = {
    state: [(re.compile(p, re.I), w) for p, w in cues] for state, cues in _CUES.items()
}

#: How far each state sits along "still evaluating" → "fully accepting".
#: This is the axis manipulation effectiveness is measured on, and it is not
#: the same as a stress axis — RESISTANT and PANICKED are both high-arousal
#: but sit at opposite ends here, which is the entire point.
_ACCEPTANCE = {
    "RESISTANT": 0.0,
    "CURIOUS": 0.15,
    "CALM": 0.30,
    "CONFUSED": 0.50,
    "FEARFUL": 0.70,
    "PANICKED": 0.80,
    "TRUSTING": 0.90,
    "COMPLIANT": 1.00,
}

#: Text-only ceiling. Mirrors coercion.py's TEXT_ONLY_CEILING for the same
#: reason: a lexical estimate must not be able to reach the confidence of one
#: backed by prosody.
TEXT_ONLY_CEILING = 0.80


@dataclass
class EmotionFeatures:
    state: str = "CALM"
    confidence: float = 0.0
    distribution: dict[str, float] = field(default_factory=dict)
    manipulation_effectiveness: float = 0.0
    trend: str = "flat"
    history: list[float] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    vector: list[float] = field(default_factory=list)


def _softmax(scores: dict[str, float], temperature: float = 0.5) -> dict[str, float]:
    import math

    if not scores:
        return {}
    mx = max(scores.values())
    exp = {k: math.exp((v - mx) / temperature) for k, v in scores.items()}
    total = sum(exp.values()) or 1.0
    return {k: v / total for k, v in exp.items()}


class EmotionTracker:
    """Tracks victim emotional state across a call."""

    STATES: ClassVar[list[str]] = list(_ACCEPTANCE)

    def __init__(self, history_len: int = 40):
        self.history: list[float] = []
        self.history_len = history_len
        self._last_state = "CALM"
        self._has_prosody = False

    def observe(
        self,
        text: str,
        *,
        pitch_var: float | None = None,
        pause_ratio: float | None = None,
        speech_rate_wpm: float | None = None,
    ) -> EmotionFeatures:
        out = EmotionFeatures()
        raw = {state: 0.0 for state in self.STATES}
        for state, patterns in _COMPILED.items():
            for pattern, weight in patterns:
                if pattern.search(text):
                    raw[state] += weight

        # Prosody, when available, disambiguates the pairs lexical cues confuse:
        # high pitch variance separates PANICKED from COMPLIANT, both of which
        # can be short and agreeable in text.
        if pitch_var is not None or speech_rate_wpm is not None:
            self._has_prosody = True
            if pitch_var is not None and pitch_var > 0.6:
                raw["PANICKED"] += 0.6
                raw["FEARFUL"] += 0.4
            if speech_rate_wpm is not None:
                if speech_rate_wpm > 190:
                    raw["PANICKED"] += 0.5
                elif speech_rate_wpm < 90:
                    raw["CONFUSED"] += 0.4
                    raw["FEARFUL"] += 0.2
        if pause_ratio is not None and pause_ratio > 0.4:
            raw["CONFUSED"] += 0.3

        if not any(raw.values()):
            # No evidence. Carry the previous state forward rather than
            # resetting to CALM — a victim does not become calm because they
            # said something unremarkable, and resetting would let a single
            # neutral turn erase an established panic.
            out.state = self._last_state
            out.confidence = 0.25
            out.distribution = {out.state: 0.25}
        else:
            distribution = _softmax(raw)
            out.distribution = {k: round(v, 3) for k, v in distribution.items() if v > 0.02}
            out.state = max(distribution, key=distribution.get)
            out.confidence = round(distribution[out.state], 3)

        acceptance = _ACCEPTANCE.get(out.state, 0.3) * out.confidence
        # Smooth against history: per-utterance emotion is jumpy, and a
        # manipulation-effectiveness number that swings 40 points on one word
        # is not something fusion can act on.
        if self.history:
            acceptance = 0.6 * acceptance + 0.4 * self.history[-1]
        if not self._has_prosody:
            acceptance = min(TEXT_ONLY_CEILING, acceptance)
            out.degraded.append("emotion:text_only")

        acceptance = round(max(0.0, min(1.0, acceptance)), 3)
        self.history.append(acceptance)
        del self.history[: max(0, len(self.history) - self.history_len)]

        out.manipulation_effectiveness = acceptance
        out.history = list(self.history)
        out.trend = self._trend()
        self._last_state = out.state
        out.vector = [round(out.distribution.get(s, 0.0), 3) for s in self.STATES] + [
            acceptance
        ]
        return out

    def _trend(self) -> str:
        if len(self.history) < 3:
            return "flat"
        delta = self.history[-1] - self.history[-3]
        if delta > 0.06:
            return "rising"
        if delta < -0.06:
            return "falling"
        return "flat"


def to_victim_state(emotion: str) -> str:
    """Map the eight-state model back onto the contract's `VictimState`.

    Needed because `VictimState` is a v1 contract field the frontend already
    renders. CURIOUS and TRUSTING both collapse to CALM here — that loss is
    exactly why the richer enum was added, and why `emotion` ships alongside
    rather than replacing it.
    """
    return {
        "CALM": "CALM",
        "CURIOUS": "CALM",
        "CONFUSED": "CONFUSED",
        "FEARFUL": "ANXIOUS",
        "PANICKED": "PANICKED",
        "TRUSTING": "CALM",
        "RESISTANT": "RESISTING",
        "COMPLIANT": "COMPLIANT",
    }.get(emotion, "UNKNOWN")
