"""
F. Behavioural features.

Per the spec: victim hesitation, agreement frequency, speech interruptions,
repeated confirmations, long pauses.

Behaviour is not emotion, and the separation is load-bearing
------------------------------------------------------------
`emotion.py` measures what the victim appears to *feel*. This measures what
they are *doing*. They dissociate, and the dissociation is diagnostic in the
dangerous direction: the highest-risk state in this entire system is a victim
who sounds calm and is behaviourally compliant, because that is a person who
has stopped resisting and is about to transfer money. An emotion-only view
reads that as "CALM — low risk" and gets it exactly backwards.

Which is why `vulnerability` here is not a restatement of fear. It rises with
compliance and repeated confirmation, and falls with resistance, regardless of
how frightened the victim sounds.

Prosodic honesty
----------------
Interruptions and pause structure are properly measurable only from word
timings. Without them, this computes lexical proxies and caps its confidence,
recording `behaviour:text_only` — the same discipline `engine/coercion.py`
already applies. A pause count inferred from punctuation is a guess, and it is
labelled as one rather than presented alongside real measurements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Explicit agreement. Distinguished from mere acknowledgement: "haan" alone is
#: backchannel, "theek hai kar deta hoon" is a commitment to act.
_AGREEMENT = [
    re.compile(p, re.I) for p in [
        r"\b(theek hai|thik hai|ok|okay|achha|acha)\b.{0,25}\b(kar|de|bhej|karta|deta)\w*",
        r"\bkar (raha|rahi|deta|deti) hoon\b",
        r"\bbhej (diya|deta|deti|raha) hoon\b",
        r"\b(ho gaya|done|sent|kar diya|bhej diya)\b",
        r"\b(haan|yes|ji) (sir|madam|ji)?\s*,?\s*(bilkul|theek|sure)\b",
        r"\b(bata|batata|batati) (deta |)hoon\b",
        r"\bmain (likh|note) (raha|rahi) hoon\b",
    ]
]

#: Hesitation markers — the victim is still processing rather than complying.
_HESITATION = [
    re.compile(p, re.I) for p in [
        r"\b(ek minute|ruk|ruko|thoda|wait|hold on|zara)\b",
        r"\b(samajh nahi|pata nahi|sure nahi|confused)\w*",
        r"\b(lekin|but|magar|phir bhi)\b",
        r"\b(sochne|soch|think|dekhta hoon|dekhti hoon)\b",
        r"\b(shayad|maybe|i guess|hmm+)\b",
        r"\.\.\.|…",
    ]
]

#: Active resistance. Weighted hardest downward — a victim who says "I'll call
#: the bank myself" has broken the spell, and that must move the number more
#: than one more compliant "haan ji".
_RESISTANCE = [
    re.compile(p, re.I) for p in [
        r"\b(nahi|no|not)\b.{0,20}\b(dunga|dungi|karunga|karungi|bataunga|give|doing)\b",
        r"\b(main (khud|self)|myself)\b.{0,25}\b(check|verify|call|dekh)\w*",
        r"\b(call back|baad mein|later|kal)\b",
        r"\b(bank|branch|police station|1930)\b.{0,20}\b(jaunga|jaungi|call|visit|jaake)\w*",
        r"\b(bete|beti|beta|husband|wife|family|bhai)\b.{0,20}\b(se|ko)\b.{0,15}\b(baat|pooch|bata)\w*",
        r"\b(ye (to |)fraud|scam|jhooth|fake)\b",
        r"\bhang(ing)? up\b|\bphone rakh\w*",
    ]
]

#: Repeated confirmation — asking the same thing again. A victim doing this is
#: seeking reassurance they are not getting, which is late-stage compliance
#: rather than resistance.
_CONFIRMATION = [
    re.compile(p, re.I) for p in [
        r"\b(phir se|again|repeat|dobara|ek baar aur)\b",
        r"\b(sach mein|really|pakka|sure)\b.{0,15}\?",
        r"\b(clear ho jayega|theek ho jayega|wapas (aa|mil) jayega)\b.{0,10}\?",
        r"\bna\?\s*$",
    ]
]

#: A gap longer than this is a pause worth counting rather than normal rhythm.
LONG_PAUSE_S = 2.0
#: Overlap greater than this means genuine interruption, not turn-taking slop.
INTERRUPTION_OVERLAP_S = 0.35


@dataclass
class BehaviourFeatures:
    hesitation: float = 0.0
    compliance: float = 0.0
    vulnerability: float = 0.0
    agreement_frequency: float = 0.0
    repeated_confirmations: int = 0
    interruptions: int = 0
    long_pauses: int = 0
    mean_pause_s: float | None = None
    resistance_events: int = 0
    degraded: list[str] = field(default_factory=list)
    vector: list[float] = field(default_factory=list)


class BehaviourTracker:
    """Accumulates behavioural signals across a call.

    Stateful because the spec's features are inherently cumulative — "agreement
    frequency" and "repeated confirmations" are counts over a conversation, not
    properties of a sentence.
    """

    def __init__(self) -> None:
        self.victim_turns = 0
        self.agreements = 0
        self.hesitations = 0
        self.resistances = 0
        self.confirmations = 0
        self.interruptions = 0
        self.long_pauses = 0
        self.pause_samples: list[float] = []
        self._last_end: float | None = None
        self._has_timings = False

    def observe(
        self,
        text: str,
        *,
        speaker: str = "VICTIM",
        t0: float | None = None,
        t1: float | None = None,
        previous_end: float | None = None,
    ) -> None:
        """Record one turn. Caller turns contribute only timing information."""
        # Interruption and pause structure are properties of the boundary
        # between turns, so they are measured for both speakers.
        end = previous_end if previous_end is not None else self._last_end
        if t0 is not None and end is not None:
            gap = t0 - end
            self._has_timings = True
            if gap < -INTERRUPTION_OVERLAP_S:
                self.interruptions += 1
            elif gap > LONG_PAUSE_S:
                self.long_pauses += 1
                self.pause_samples.append(gap)
            elif gap >= 0:
                self.pause_samples.append(gap)
        if t1 is not None:
            self._last_end = t1

        if speaker != "VICTIM":
            return

        self.victim_turns += 1
        if any(p.search(text) for p in _AGREEMENT):
            self.agreements += 1
        if any(p.search(text) for p in _HESITATION):
            self.hesitations += 1
        if any(p.search(text) for p in _RESISTANCE):
            self.resistances += 1
        if any(p.search(text) for p in _CONFIRMATION):
            self.confirmations += 1

    def snapshot(self) -> BehaviourFeatures:
        out = BehaviourFeatures()
        turns = max(1, self.victim_turns)

        out.agreement_frequency = round(min(1.0, self.agreements / turns), 3)
        out.hesitation = round(min(1.0, self.hesitations / turns), 3)
        out.repeated_confirmations = self.confirmations
        out.interruptions = self.interruptions
        out.long_pauses = self.long_pauses
        out.resistance_events = self.resistances

        if self.pause_samples:
            out.mean_pause_s = round(
                sum(self.pause_samples) / len(self.pause_samples), 2
            )

        # Compliance: agreement net of resistance. Resistance subtracts at
        # roughly 1.5x because breaking the spell is harder than maintaining it,
        # and a single genuine push-back is more informative than a single "ok".
        raw_compliance = (self.agreements - 1.5 * self.resistances) / turns
        out.compliance = round(max(0.0, min(1.0, raw_compliance)), 3)

        # Vulnerability is the composite the fusion engine consumes. Repeated
        # confirmation is included because it is the tell of someone who has
        # already decided to comply and is looking for permission.
        vulnerability = (
            0.45 * out.compliance
            + 0.20 * min(1.0, self.confirmations / 3.0)
            + 0.15 * out.hesitation
            + 0.20 * min(1.0, self.long_pauses / 4.0)
        )
        # Resistance caps vulnerability outright. A victim actively pushing
        # back is not vulnerable in the sense that matters here, however
        # hesitant they sound.
        if self.resistances >= 2:
            vulnerability = min(vulnerability, 0.35)
        elif self.resistances == 1:
            vulnerability = min(vulnerability, 0.6)
        out.vulnerability = round(max(0.0, min(1.0, vulnerability)), 3)

        if not self._has_timings:
            out.degraded.append("behaviour:text_only")

        out.vector = [
            out.hesitation,
            out.compliance,
            out.vulnerability,
            out.agreement_frequency,
            round(min(1.0, self.confirmations / 5.0), 3),
            round(min(1.0, self.interruptions / 5.0), 3),
            round(min(1.0, self.long_pauses / 5.0), 3),
            round(min(1.0, self.resistances / 3.0), 3),
        ]
        return out
