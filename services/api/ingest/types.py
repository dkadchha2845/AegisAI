"""
Shared input types for the ingest layer.

These sit between "whatever the user sent" and "what the feature extractors
expect". Keeping them as plain dataclasses rather than Pydantic models is
deliberate — they never cross the wire, and the engine layer is dataclass-only
so that importing it does not drag Pydantic into the ML pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Modality(str, Enum):
    AUDIO = "AUDIO"
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    METADATA = "METADATA"


@dataclass
class RawInput:
    """One inbound artifact, before any processing.

    Exactly one of `text` / `blob` is expected to be set. `blob` is bytes
    rather than a path because the upload path already reads the file into
    memory (capped at 4MB by the route), and writing it to disk just to read it
    back would add a failure mode for no benefit.
    """

    modality: Modality
    text: Optional[str] = None
    blob: Optional[bytes] = None
    filename: Optional[str] = None
    #: Caller ID, platform, device, timestamps — anything about the envelope
    #: rather than the content. Consumed by ingest/metadata.py.
    metadata: dict = field(default_factory=dict)
    #: Hint from the caller. Ignored if it conflicts with what we detect.
    speaker_hint: Optional[str] = None


@dataclass
class Turn:
    """One utterance after diarization, ready for the feature extractors."""

    speaker: str  # CALLER | VICTIM
    text: str
    t0: Optional[float] = None
    t1: Optional[float] = None
    #: Set when the ASR backend returned per-word timings. The behavioural and
    #: emotional extractors both degrade to lexical-only without these, and say
    #: so rather than inventing prosody.
    word_timings: Optional[list[tuple[str, float, float]]] = None
    confidence: float = 1.0
