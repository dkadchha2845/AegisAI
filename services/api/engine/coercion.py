"""
Coercion index — victim stress, measured independently of the text classifier.

The independence is the point. If the coercion index were derived from the
stage labels it would be a restatement of the classifier wearing a different
hat, and fusing the two would be double-counting. It reads the *victim's* side
of the call — timing, rate, hesitation, compliance language — while the stage
classifier reads the *caller's*. The ablation in the deck is only meaningful
because the two signals can disagree.

Live audio supplies pitch variance and pause ratio from the ASR word timings.
When only text is available (the upload path, or ASR degraded to a local
model) the prosodic features are absent, and the index is computed from the
lexical features alone with `coercion:text_only` recorded. It is deliberately
capped lower in that mode — a text-only stress estimate should never be able
to reach the same ceiling as one backed by audio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Victim-side language that indicates the caller is winning.
COMPLIANCE_CUES = [
    r"\b(theek hai|ok|okay|haan|yes)\b.*\b(kar|de|bhej)\w*",
    r"\bkar (raha|rahi) hoon\b",
    r"\bbhej (diya|deta|deti) hoon\b",
    r"\b(bata|batata|batati) hoon\b",
    r"\bsorry sir\b",
    r"\bmaaf k\w+\b",
]

# Language that indicates the victim is still thinking.
RESISTANCE_CUES = [
    r"\b(nahi|no|why|kyun|kyu)\b",
    r"\b(main check|verify kar|call back|baad mein)\w*",
    r"\b(bank jaunga|branch jaunga|police station)\b",
    r"\b(bete|beti|husband|wife|family) se (baat|pooch)\w*",
]

DISTRESS_CUES = [
    r"\b(please|pleej|bhagwan|god)\b",
    r"\b(dar lag|ghabra|tension|pareshan)\w*",
    r"\b(kya karu|kya karna hoga|help)\b",
    r"\b(jail|arrest)\b.*\?",
]

_COMPLIANCE = [re.compile(p, re.I) for p in COMPLIANCE_CUES]
_RESISTANCE = [re.compile(p, re.I) for p in RESISTANCE_CUES]
_DISTRESS = [re.compile(p, re.I) for p in DISTRESS_CUES]

TEXT_ONLY_CEILING = 72.0


@dataclass
class CoercionOut:
    index: float
    trend: str
    history: list[float]
    features: dict[str, float]
    victim_state: str
    degraded: list[str] = field(default_factory=list)


class CoercionTracker:
    """Stateful across a call — trend needs memory, and so does the ratchet."""

    def __init__(self, history_len: int = 40):
        self.history: list[float] = []
        self.history_len = history_len
        self.compliance_hits = 0
        self.resistance_hits = 0

    def observe(
        self,
        text: str,
        *,
        duration_s: float | None = None,
        word_count: int | None = None,
        pause_ratio: float | None = None,
        pitch_var: float | None = None,
    ) -> CoercionOut:
        degraded: list[str] = []
        words = word_count if word_count is not None else len(text.split())

        compliance = sum(1 for p in _COMPLIANCE if p.search(text))
        resistance = sum(1 for p in _RESISTANCE if p.search(text))
        distress = sum(1 for p in _DISTRESS if p.search(text))
        self.compliance_hits += compliance
        self.resistance_hits += resistance

        features: dict[str, float] = {
            "compliance_hits": float(self.compliance_hits),
            "resistance_hits": float(self.resistance_hits),
            "distress_hits": float(distress),
        }

        # Lexical component: compliance and distress raise it, resistance
        # lowers it. Resistance is weighted hardest — a victim who says "let
        # me call the bank" has broken the spell, and that should move the
        # needle more than one more "haan ji".
        lexical = 22.0 * compliance + 26.0 * distress - 30.0 * resistance
        lexical = max(0.0, min(100.0, 30.0 + lexical))

        prosodic: float | None = None
        if pause_ratio is not None or pitch_var is not None or duration_s:
            parts: list[float] = []
            if duration_s and words:
                wpm = words / max(duration_s, 0.1) * 60
                features["speech_rate_wpm"] = round(wpm, 1)
                # Both extremes signal stress: racing, or halting.
                parts.append(min(100.0, abs(wpm - 140.0) * 0.8))
            if pause_ratio is not None:
                features["pause_ratio"] = round(pause_ratio, 3)
                parts.append(min(100.0, pause_ratio * 180))
            if pitch_var is not None:
                features["pitch_var"] = round(pitch_var, 3)
                parts.append(min(100.0, pitch_var * 100))
            if parts:
                prosodic = sum(parts) / len(parts)

        if prosodic is None:
            degraded.append("coercion:text_only")
            index = min(TEXT_ONLY_CEILING, lexical)
        else:
            index = 0.6 * lexical + 0.4 * prosodic

        # Smooth against the previous value. Raw per-utterance stress is
        # jumpy, and a sparkline that spikes on every turn is unreadable.
        if self.history:
            index = 0.65 * index + 0.35 * self.history[-1]

        index = round(max(0.0, min(100.0, index)), 1)
        self.history.append(index)
        del self.history[: max(0, len(self.history) - self.history_len)]

        return CoercionOut(
            index=index,
            trend=self._trend(),
            history=list(self.history),
            features=features,
            victim_state=self._victim_state(index, compliance, resistance, distress),
            degraded=degraded,
        )

    def _trend(self) -> str:
        if len(self.history) < 3:
            return "flat"
        delta = self.history[-1] - self.history[-3]
        if delta > 4:
            return "rising"
        if delta < -4:
            return "falling"
        return "flat"

    @staticmethod
    def _victim_state(
        index: float, compliance: int, resistance: int, distress: int
    ) -> str:
        # Resistance is checked first and unconditionally: a victim pushing
        # back is the single most important state for the coach to know
        # about, and it must not be masked by a high index carried over from
        # the panic that preceded it.
        if resistance:
            return "RESISTING"
        if compliance and index > 55:
            return "COMPLIANT"
        if distress or index > 75:
            return "PANICKED"
        if index > 55:
            return "ANXIOUS"
        if index > 35:
            return "CONFUSED"
        if index > 0:
            return "CALM"
        return "UNKNOWN"
