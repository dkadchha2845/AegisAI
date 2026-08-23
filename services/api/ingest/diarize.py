"""
Speaker diarization — deciding which side of the call each utterance came from.

    pyannote.audio  → preferred, when audio and a HF token are both present.
    lexical role assignment → always available.

Why the fallback is more than a placeholder
-------------------------------------------
This system does not need to know *who* is speaking in the biometric sense. It
needs exactly one bit per turn: CALLER or VICTIM. And in a scam call those two
roles are lexically separable to a degree that would be unusual anywhere else —
the caller issues instructions, claims authority, and demands; the victim
questions, complies, and pleads. `engine/classifier.py` and `engine/coercion.py`
are already built on that asymmetry.

So the fallback scores role-indicative language rather than guessing by turn
parity. Parity alone breaks on the very calls that matter most: a scammer who
talks for four consecutive turns while the victim stays silent is the shape of
a successful isolation, and alternating assignment would relabel half of it as
the victim and hand the coercion tracker the scammer's words.

Getting this wrong is expensive in a specific direction. Victim text drives the
coercion index; caller text drives the stage classifier and the Trust Passport.
Swapping them makes a frightened victim look like an escalating scammer.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .types import Turn

# --- Role-indicative language ---------------------------------------------
# Weighted because the signals are not equally diagnostic. "bataiye" (tell me)
# is a strong caller marker; a question mark alone is weak.

_CALLER_CUES: list[tuple[str, float]] = [
    (r"\b(main|hum)\b.*\b(bol|baat) raha\b", 1.0),
    (r"\b(cbi|rbi|trai|ncb|cyber ?crime|income tax|enforcement directorate)\b", 1.2),
    (r"\b(inspector|officer|acp|dcp|constable|sub[- ]?inspector)\b", 1.0),
    (r"\b(bataiye|batao|kariye|karo|kijiye|dijiye|daaliye|bhejiye|suniye)\b", 0.9),
    (r"\b(aapke|aapka|aapki|aapko)\b", 0.5),
    (r"\b(warrant|arrest|case|fir|non[- ]?bailable|money laundering)\b", 0.8),
    (r"\b(transfer|deposit|account number|ifsc|otp|verification)\b", 0.6),
    (r"\b(mat kariye|mat bataiye|disconnect mat|confidential)\b", 1.0),
    (r"\b(badge|case (number|id)|section \d+)\b", 0.9),
]

_VICTIM_CUES: list[tuple[str, float]] = [
    (r"\b(maine|mujhe|mera|meri|main to)\b", 0.9),
    (r"\b(kya karu|kya karna|samajh nahi|pata nahi)\b", 1.1),
    (r"\b(sir|madam|ji)\b\s*$", 0.4),
    (r"\b(theek hai|haan ji|achha|ok|okay)\b", 0.6),
    (r"\b(dar lag|ghabra|pareshan|tension)\w*", 1.1),
    (r"\b(nahi kiya|kuch nahi|maine to kuch)\b", 1.2),
    (r"\b(please|bhagwan|maaf)\b", 0.8),
    (r"\b(ek minute|ruk|thoda)\b", 0.5),
    (r"\?\s*$", 0.3),
]

_CALLER = [(re.compile(p, re.I), w) for p, w in _CALLER_CUES]
_VICTIM = [(re.compile(p, re.I), w) for p, w in _VICTIM_CUES]

#: A silence this long between turns is a pause worth recording rather than
#: ordinary conversational rhythm. Read by the behavioural extractor.
LONG_PAUSE_S = 2.0


@dataclass
class DiarizationResult:
    turns: list[Turn]
    backend: str
    degraded: list[str] = field(default_factory=list)
    #: 0-1, mean per-turn confidence in the role assignment.
    confidence: float = 0.0


def _role_scores(text: str) -> tuple[float, float]:
    caller = sum(w for p, w in _CALLER if p.search(text))
    victim = sum(w for p, w in _VICTIM if p.search(text))
    return caller, victim


def assign_roles(texts: list[str], first_speaker: str = "CALLER") -> DiarizationResult:
    """Assign CALLER/VICTIM to a list of utterances using role language.

    `first_speaker` seeds the prior: on an inbound scam call the caller speaks
    first essentially always, so an opening turn with no role signal is far
    more likely theirs than the victim's.
    """
    turns: list[Turn] = []
    confidences: list[float] = []
    previous = None

    for i, text in enumerate(texts):
        caller, victim = _role_scores(text)

        if caller == victim == 0:
            # No lexical signal. Alternate from the previous turn — with no
            # evidence, a change of speaker is the better prior than a repeat.
            speaker = (
                first_speaker
                if previous is None
                else ("VICTIM" if previous == "CALLER" else "CALLER")
            )
            confidence = 0.35 if i else 0.6
        else:
            speaker = "CALLER" if caller >= victim else "VICTIM"
            total = caller + victim
            confidence = 0.5 + 0.5 * (abs(caller - victim) / total) if total else 0.5

        turns.append(Turn(speaker=speaker, text=text, confidence=round(confidence, 3)))
        confidences.append(confidence)
        previous = speaker

    return DiarizationResult(
        turns=turns,
        backend="lexical_roles",
        degraded=["diarization:lexical"],
        confidence=round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
    )


def _pyannote_available() -> bool:
    if not os.getenv("HUGGINGFACE_TOKEN") and not os.getenv("HF_TOKEN"):
        # The pretrained pipeline is gated; without a token the load fails at
        # runtime with a 401 that reads like a bug. Checking here is clearer.
        return False
    try:
        import pyannote.audio  # noqa: F401
        return True
    except ImportError:
        return False


def diarize_audio(audio_path: str, segments: list) -> DiarizationResult | None:
    """True audio diarization. Returns None if unavailable, so the caller falls
    back to lexical role assignment over the ASR segments."""
    if not _pyannote_available():
        return None
    try:
        from pyannote.audio import Pipeline  # type: ignore

        token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=token
        )
        annotation = pipeline(audio_path)

        # pyannote returns anonymous speaker labels (SPEAKER_00/01). Mapping
        # them to roles still needs the lexical signal — biometrics tell you
        # there are two people, not which one is impersonating the police.
        speaker_text: dict[str, list[str]] = {}
        for segment in segments:
            mid = (segment.start + segment.end) / 2
            label = "SPEAKER_00"
            for turn, _, spk in annotation.itertracks(yield_label=True):
                if turn.start <= mid <= turn.end:
                    label = spk
                    break
            speaker_text.setdefault(label, []).append(segment.text)

        scored = {
            label: _role_scores(" ".join(texts)) for label, texts in speaker_text.items()
        }
        caller_label = max(
            scored, key=lambda lab: scored[lab][0] - scored[lab][1], default=None
        )

        turns: list[Turn] = []
        for segment in segments:
            mid = (segment.start + segment.end) / 2
            label = "SPEAKER_00"
            for turn, _, spk in annotation.itertracks(yield_label=True):
                if turn.start <= mid <= turn.end:
                    label = spk
                    break
            turns.append(
                Turn(
                    speaker="CALLER" if label == caller_label else "VICTIM",
                    text=segment.text,
                    t0=segment.start,
                    t1=segment.end,
                    word_timings=segment.words or None,
                    confidence=0.9,
                )
            )
        return DiarizationResult(turns=turns, backend="pyannote", degraded=[], confidence=0.9)
    except Exception as exc:
        print(f"[aegis] pyannote diarization failed ({exc}); using lexical roles")
        return None


def status() -> dict:
    return {
        "backend": "pyannote" if _pyannote_available() else "lexical_roles",
        "available": True,
    }
