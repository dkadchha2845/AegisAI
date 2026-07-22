"""
Input processing pipeline — the spec's Section 4, assembled.

    Audio  → Whisper → transcript ─┐
    Image  → OCR     → text       ─┤
    Video  → metadata extraction  ─┼→ language detection → diarization
    Text   → (direct)             ─┤   → cleaning → normalization
    Metadata → envelope intel     ─┘   → ready for feature extraction

One function, `process_input`, is the whole public surface. Everything upstream
of the feature extractors goes through it, so there is exactly one place where
"what did the user actually send us" is decided — and exactly one place that
has to be correct about degradation.

The ordering is not arbitrary. Language detection runs *before* diarization
because the role-assignment cues are Hinglish-specific and would score
near-zero on out-of-scope text, silently producing confident nonsense. And
normalisation runs *after* diarization because the speaker prefixes it strips
("Caller:") are exactly what makes diarization trivial when they are present.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..engine import ocr
from . import asr, diarize, language, metadata as metadata_mod, normalize
from .types import Modality, RawInput, Turn


@dataclass
class ProcessedInput:
    """What the feature extractors receive, regardless of what came in."""

    turns: list[Turn] = field(default_factory=list)
    language: str = "und"
    language_confidence: float = 0.0
    script: str = "latin"
    envelope: metadata_mod.EnvelopeIntel = field(default_factory=metadata_mod.EnvelopeIntel)
    #: QR payloads pulled out of images — routed straight to engine/upi.py.
    qr_payloads: list[str] = field(default_factory=list)
    #: True when word-level timings survived, which is what lets the coercion
    #: and behaviour layers use prosody instead of lexical cues alone.
    has_timings: bool = False

    @property
    def full_text(self) -> str:
        return "\n".join(f"{t.speaker}: {t.text}" for t in self.turns)

    @property
    def caller_text(self) -> str:
        return " ".join(t.text for t in self.turns if t.speaker == "CALLER")

    @property
    def victim_text(self) -> str:
        return " ".join(t.text for t in self.turns if t.speaker == "VICTIM")


@dataclass
class IngestResult:
    ok: bool
    processed: ProcessedInput
    backends: dict = field(default_factory=dict)
    degraded: list[str] = field(default_factory=list)
    #: Set when `ok` is False. Written for the person who sent the input, and
    #: always names the thing they can do instead.
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def _from_text(raw_text: str, speaker_hint: str | None) -> tuple[list[Turn], list[str]]:
    """Text → turns. Uses explicit speaker labels when present, roles when not."""
    lines = normalize.split_utterances(raw_text)
    if not lines:
        return [], []

    # If the paste is already labelled, that beats any inference we could do.
    stripped: list[str] = []
    labels: list[str | None] = []
    for line in lines:
        text, had_prefix = normalize.strip_speaker_prefix(line)
        if had_prefix:
            lowered = line.lower()
            is_caller = any(
                w in lowered.split(":")[0] for w in
                ("caller", "scammer", "agent", "fraudster", "unknown", "speaker 1")
            )
            labels.append("CALLER" if is_caller else "VICTIM")
        else:
            labels.append(None)
        stripped.append(normalize.normalize(text, strip_prefix=False).text)

    stripped = [s for s in stripped if s]
    if not stripped:
        return [], []

    if all(label is not None for label in labels) and len(labels) == len(stripped):
        return (
            [Turn(speaker=lab or "CALLER", text=txt, confidence=1.0)
             for lab, txt in zip(labels, stripped)],
            [],
        )

    result = diarize.assign_roles(stripped, first_speaker=speaker_hint or "CALLER")
    return result.turns, result.degraded


def process_input(raw: RawInput) -> IngestResult:
    """Convert one inbound artifact into feature-extraction-ready structure."""
    degraded: list[str] = []
    warnings: list[str] = []
    backends: dict = {}
    text_for_analysis = ""
    turns: list[Turn] = []
    qr_payloads: list[str] = []
    has_timings = False

    envelope = metadata_mod.extract(raw.metadata)
    backends["metadata"] = "builtin"

    # --- Audio ------------------------------------------------------------
    if raw.modality is Modality.AUDIO:
        if not raw.blob:
            return IngestResult(
                False, ProcessedInput(envelope=envelope),
                reason="No audio content was supplied.",
            )
        result = asr.transcribe(raw.blob, raw.filename)
        backends["asr"] = result.backend
        degraded += result.degraded
        if not result.ok:
            return IngestResult(
                False, ProcessedInput(envelope=envelope), backends=backends,
                degraded=degraded, reason=result.reason,
            )
        text_for_analysis = result.text
        has_timings = result.has_word_timings
        if not has_timings:
            # Said out loud rather than inferred downstream: both the coercion
            # index and the behavioural extractor cap themselves lower without
            # timings, and the UI explains why using this tag.
            degraded.append("coercion:text_only")

        # Prefer true diarization; fall back to lexical roles over the ASR
        # segments, which still gives per-segment timings.
        diarized = diarize.diarize_audio(raw.filename or "", result.segments)
        if diarized is None:
            segment_texts = [normalize.normalize(s.text).text for s in result.segments]
            segment_texts = [t for t in segment_texts if t]
            lexical = diarize.assign_roles(segment_texts)
            for turn, segment in zip(lexical.turns, result.segments):
                turn.t0, turn.t1 = segment.start, segment.end
                turn.word_timings = segment.words or None
            turns = lexical.turns
            backends["diarization"] = lexical.backend
            degraded += lexical.degraded
        else:
            turns = diarized.turns
            for turn in turns:
                turn.text = normalize.normalize(turn.text).text
            turns = [t for t in turns if t.text]
            backends["diarization"] = diarized.backend
            degraded += diarized.degraded

    # --- Image ------------------------------------------------------------
    elif raw.modality is Modality.IMAGE:
        if not raw.blob:
            return IngestResult(
                False, ProcessedInput(envelope=envelope),
                reason="No image content was supplied.",
            )
        result = ocr.extract_text(raw.blob)
        backends["ocr"] = result.engine
        degraded += result.degraded
        qr_payloads = result.qr_payloads
        if not result.text and "ocr:failed" in result.degraded:
            return IngestResult(
                False, ProcessedInput(envelope=envelope, qr_payloads=qr_payloads),
                backends=backends, degraded=degraded, reason="Could not read this image. Paste the text instead.",
            )
        text_for_analysis = result.text
        if ocr.looks_like_payment_confirmation(text_for_analysis):
            warnings.append(
                "This looks like a payment confirmation. If money has already "
                "moved, report it on 1930 immediately — the first few hours are "
                "when a transfer can still be frozen."
            )
        turns, extra = _from_text(text_for_analysis, raw.speaker_hint)
        degraded += extra

    # --- Video ------------------------------------------------------------
    elif raw.modality is Modality.VIDEO:
        # Frame analysis is not implemented; the envelope still is. Reporting
        # the metadata we do have beats refusing the whole input.
        backends["video"] = "metadata_only"
        degraded.append("video:metadata_only")
        text_for_analysis = raw.text or ""
        if text_for_analysis:
            turns, extra = _from_text(text_for_analysis, raw.speaker_hint)
            degraded += extra

    # --- Text / metadata-only --------------------------------------------
    else:
        text_for_analysis = raw.text or ""
        if text_for_analysis.strip():
            turns, extra = _from_text(text_for_analysis, raw.speaker_hint)
            degraded += extra
        backends["text"] = "builtin"

    if not turns and raw.modality is not Modality.METADATA:
        return IngestResult(
            False,
            ProcessedInput(envelope=envelope, qr_payloads=qr_payloads),
            backends=backends,
            degraded=degraded,
            reason=(
                "Nothing readable was found in this input. Paste the message text "
                "directly — that path always works."
            ),
            warnings=warnings,
        )

    # --- Language ---------------------------------------------------------
    combined = text_for_analysis or " ".join(t.text for t in turns)
    lang = language.detect(combined)
    backends["language"] = lang.backend
    degraded += lang.degraded
    if not language.is_supported(lang):
        # Flagged, not rejected: the mechanical checks (UPI structure, payment
        # framing) are language-independent and still worth running. Only the
        # trained stage classifier is out of scope, and the warning says so.
        warnings.append(
            f"Detected language '{lang.language}', which this build was not "
            "trained on. Stage labels for this input are unreliable; the "
            "structural payment and identity checks still apply."
        )
        degraded.append("lang:unsupported")

    processed = ProcessedInput(
        turns=turns,
        language=lang.language,
        language_confidence=lang.confidence,
        script=lang.script,
        envelope=envelope,
        qr_payloads=qr_payloads,
        has_timings=has_timings,
    )
    # Dedupe while preserving order — the same tag can legitimately be added by
    # two stages, and a repeated tag reads like two separate problems.
    seen: list[str] = []
    for tag in degraded:
        if tag not in seen:
            seen.append(tag)

    return IngestResult(
        ok=True, processed=processed, backends=backends, degraded=seen, warnings=warnings
    )


def status() -> dict:
    """Backend availability for /api/health."""
    return {
        "asr": asr.status(),
        "ocr": ocr.status(),
        "language": language.status(),
        "diarization": diarize.status(),
    }
