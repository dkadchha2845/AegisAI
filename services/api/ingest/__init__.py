"""
KAVACH Module 1 — Input Processing Layer.

Turns every supported input format (audio, text, image, video metadata) into
one structured, machine-readable shape the feature extractors can consume.

The organising rule for this whole package
------------------------------------------
Every adapter here wraps a heavy optional dependency — Whisper, PaddleOCR,
pyannote, fastText, spaCy — and every one of them has a working fallback that
requires nothing but the standard library. That is not hedging: the rest of
PRESAGE already guarantees that the request path makes no network call and
needs no GPU, and an input layer that breaks that guarantee would break it for
the entire product, not just for itself.

So each adapter reports which backend actually served, and records a
degradation tag when it was not the good one. A transcript produced by a
fallback is still a transcript; a transcript that silently pretends to be
Whisper output when it is not is a lie the classifier downstream cannot detect.
"""

from .pipeline import IngestResult, ProcessedInput, process_input
from .types import Modality, RawInput

__all__ = [
    "IngestResult",
    "Modality",
    "ProcessedInput",
    "RawInput",
    "process_input",
]
