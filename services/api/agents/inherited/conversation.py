"""
What "the conversation" is, for an investigation — decided once.

**Why it exists.** Six of the seven adapters need the same thing: the caller's
turns and the victim's turns, in order. If each worked it out for itself there
would be six answers to one question, and the first time they disagreed the
symptom would be a fused score that no individual agent could account for. It is
also the join between two shapes: the batch path scores a *string*, and an
investigation carries `inputs`, `extracted_text` and a `transcript`.

**What it consumes.** `InvestigationState`.

**What it outputs.** Ordered `(speaker, text)` turns, plus the small derived
reads the adapters want — the caller's words as one blob, and any phone number
submitted as evidence.

**How it connects.** Every adapter in this package calls it; nothing else does.
The parsing itself is delegated to `engine/analyzer.normalise`, deliberately:
that function decides speaker attribution, JSON transcript handling, alternation
and one-sided sentence splitting, and those decisions are exactly what the two
paths have to share for the equivalence test to mean anything. Reimplementing
them here would make the test compare two implementations of the same idea
rather than one implementation reached two ways.

**How it is evaluated.** `test_inherited_agents.py` asserts the turns produced
from a state equal `normalise()` on the same raw text, including the one-sided
and JSON-transcript cases.

**Limitations, stated.** Text only. A screenshot's words arrive here once the
OCR agent (2.2) writes them into `extracted_text`, and a recording's once the
ASR agent does; until then an image-only investigation yields no turns and every
adapter in this package skips, which is the correct outcome — see the note in
`inherited/__init__.py` about what the graph currently does with a skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from schema.models import InputType, InvestigationState

from ...engine.analyzer import normalise

#: Evidence that is a bare identifier rather than something anybody said. A
#: submitted phone number is evidence for the spoofing agent and is not a line
#: of dialogue; folding it into the transcript would have the stage classifier
#: labelling "+919812345678" as a conversational turn. Identifiers *inside* a
#: message are untouched — they are part of what was said.
_NOT_DIALOGUE = frozenset({InputType.PHONE, InputType.UPI_ID, InputType.URL, InputType.QR})

CALLER = "CALLER"
VICTIM = "VICTIM"


@dataclass(frozen=True)
class Turn:
    """One utterance, with the position it held in the conversation.

    `index` is the position across *both* speakers, so a finding can point at
    "the fourth turn" and mean the same thing to every adapter and to the UI.
    """

    index: int
    speaker: str
    text: str


def source_text(state: InvestigationState) -> str:
    """The conversation this investigation is about, as one string.

    Three sources, in order of how much processing has been done to them: a
    parsed `transcript` if some agent produced one, then `extracted_text` (OCR
    and ASR write here), then the inline text of the evidence items themselves.
    The first non-empty one wins rather than all three being concatenated —
    `extracted_text` is *derived from* the inputs, so using both would score the
    same words twice and inflate every cumulative signal in the engine.
    """
    # `final` only. `Transcript.partial` is in-flight ASR text the contract
    # describes as "never scored", and a half-finished sentence produces a label
    # that flips as the rest of it arrives.
    if state.transcript is not None and state.transcript.final:
        return "\n".join(f"{u.speaker}: {u.text}" for u in state.transcript.final if u.text)

    if state.extracted_text:
        chunks = [e.text for e in state.extracted_text if e.text and e.text.strip()]
        if chunks:
            return "\n".join(chunks)

    parts = [
        item.text
        for item in state.inputs
        if item.text and item.text.strip() and item.kind not in _NOT_DIALOGUE
    ]
    return "\n".join(parts)


def turns(state: InvestigationState) -> List[Turn]:
    """Every utterance, attributed and in order.

    `normalise` is the old path's own parser. Sharing it is what makes "the
    graph and the analyzer see the same conversation" a fact rather than an
    intention.
    """
    raw = source_text(state)
    if not raw.strip():
        return []
    return [Turn(i, speaker, text) for i, (speaker, text) in enumerate(normalise(raw))]


def caller_turns(state: InvestigationState) -> List[Turn]:
    return [t for t in turns(state) if t.speaker == CALLER]


def victim_turns(state: InvestigationState) -> List[Turn]:
    return [t for t in turns(state) if t.speaker == VICTIM]


def has_caller_speech(state: InvestigationState) -> bool:
    """The `can_handle` most of this package shares."""
    return bool(caller_turns(state))


def claimed_identity_text(state: InvestigationState) -> str:
    """Everything the caller said, as the raw material for an identity claim.

    `spoofing.analyze_number` documents `claimed_identity` as "the raw text the
    caller used to introduce themselves (or a resolved label)", so handing it
    the caller's words is a supported use rather than a shortcut. It also keeps
    the spoofing agent independent of the Trust Passport: taking the *resolved*
    label would mean one agent reading another's output for something it can
    determine from the evidence itself.
    """
    return " ".join(t.text for t in caller_turns(state))


def phone_numbers(state: InvestigationState) -> List[str]:
    """Numbers this investigation was actually given, in a stable order.

    Two sources, both explicit. `entities.phones` is the contract field the
    entity extraction of 2.1/3.2 will fill; until then the only way a number
    reaches an investigation is as its own evidence item, which the 1.4
    classifier types `PHONE`. Numbers merely *mentioned* inside a message are
    deliberately not scraped here — pulling identifiers out of text is an
    extraction agent's job, and a regex in this file would be a second, unowned
    implementation of it.
    """
    found: List[str] = []
    seen: set[str] = set()
    for value in _ordered(state.entities.phones):
        if value not in seen:
            seen.add(value)
            found.append(value)
    for item in state.inputs:
        if item.kind is InputType.PHONE and item.text:
            value = item.text.strip()
            if value and value not in seen:
                seen.add(value)
                found.append(value)
    return found


def _ordered(values: Sequence[str]) -> List[str]:
    return [v.strip() for v in values if v and v.strip()]


__all__ = [
    "CALLER",
    "VICTIM",
    "Turn",
    "caller_turns",
    "claimed_identity_text",
    "has_caller_speech",
    "phone_numbers",
    "source_text",
    "turns",
    "victim_turns",
]
