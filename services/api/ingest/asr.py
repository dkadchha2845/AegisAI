"""
Speech-to-text adapter.

    faster-whisper  → preferred. Local, no network, word-level timings.
    openai-whisper  → accepted if faster-whisper is absent.
    null            → returns nothing and says so.

The null backend is the important one to understand. When no ASR is installed,
this does **not** return an empty transcript that the classifier would then
score as BENIGN — an empty string is not evidence of a safe call, and scoring
it as one is the single most harmful thing this layer could do. It returns
`ok=False` with a reason, and the caller surfaces that instead of a verdict.

Word timings matter more than they look. `engine/coercion.py` and the AegisAI
behavioural extractor both read pause structure and speech rate off them, and
both explicitly cap their output lower when the timings are absent. So the
adapter reports whether it produced them rather than letting the consumer
guess from an empty list.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: Whisper model size. `base` is the deliberate default: `small` and above are
#: meaningfully better on accented Indian English but download 500MB+, and this
#: layer must stay usable on a laptop that has never run it before.
DEFAULT_MODEL = "base"


@dataclass
class ASRSegment:
    text: str
    start: float
    end: float
    words: list[tuple[str, float, float]] = field(default_factory=list)


@dataclass
class ASRResult:
    ok: bool
    backend: str
    segments: list[ASRSegment] = field(default_factory=list)
    language: Optional[str] = None
    #: Why this failed, when it did. Shown to the user, so it names the fix.
    reason: Optional[str] = None
    degraded: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def has_word_timings(self) -> bool:
        return any(s.words for s in self.segments)


class ASRBackend:
    name = "abstract"

    def available(self) -> bool:
        raise NotImplementedError

    def transcribe(self, audio: bytes, filename: str | None = None) -> ASRResult:
        raise NotImplementedError


class FasterWhisperBackend(ASRBackend):
    """CTranslate2 Whisper. 4x faster than the reference implementation on CPU
    and the only one of the two that is comfortable in a request path."""

    name = "faster-whisper"

    def __init__(self, model_size: str = DEFAULT_MODEL):
        self.model_size = model_size
        self._model = None

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore

            # int8 on CPU: roughly half the memory, no measurable accuracy cost
            # at this model size, and it keeps a 4-core laptop responsive.
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio: bytes, filename: str | None = None) -> ASRResult:
        suffix = Path(filename).suffix if filename else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio)
            tmp.flush()
            model = self._load()
            segments, info = model.transcribe(
                tmp.name,
                word_timestamps=True,
                # Hindi rather than auto-detect: the corpus is Hinglish, and
                # Whisper's detector routinely calls code-mixed speech English,
                # which then drops the Hindi half of every sentence.
                language="hi",
                vad_filter=True,
            )
            out: list[ASRSegment] = []
            for seg in segments:
                words = [
                    (w.word.strip(), float(w.start), float(w.end))
                    for w in (getattr(seg, "words", None) or [])
                ]
                out.append(
                    ASRSegment(
                        text=seg.text, start=float(seg.start), end=float(seg.end), words=words
                    )
                )
        return ASRResult(
            ok=True,
            backend=self.name,
            segments=out,
            language=getattr(info, "language", None),
        )


class OpenAIWhisperBackend(ASRBackend):
    """Reference Whisper. Accepted, but slower and heavier than the CT2 build."""

    name = "openai-whisper"

    def __init__(self, model_size: str = DEFAULT_MODEL):
        self.model_size = model_size
        self._model = None

    def available(self) -> bool:
        try:
            import whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def transcribe(self, audio: bytes, filename: str | None = None) -> ASRResult:
        import whisper  # type: ignore

        if self._model is None:
            self._model = whisper.load_model(self.model_size)
        suffix = Path(filename).suffix if filename else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio)
            tmp.flush()
            result = self._model.transcribe(tmp.name, language="hi", word_timestamps=True)
        segments = [
            ASRSegment(
                text=s.get("text", ""),
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                words=[
                    (w.get("word", "").strip(), float(w.get("start", 0)), float(w.get("end", 0)))
                    for w in s.get("words", []) or []
                ],
            )
            for s in result.get("segments", [])
        ]
        return ASRResult(
            ok=True, backend=self.name, segments=segments, language=result.get("language")
        )


class NullASRBackend(ASRBackend):
    """No ASR installed. Declines rather than inventing a transcript."""

    name = "none"

    def available(self) -> bool:
        return True

    def transcribe(self, audio: bytes, filename: str | None = None) -> ASRResult:
        return ASRResult(
            ok=False,
            backend=self.name,
            reason=(
                "No speech-to-text backend is installed, so this audio cannot be "
                "read. Install faster-whisper (`pip install faster-whisper`) or "
                "paste the transcript text directly — the text path is fully "
                "supported and scores identically."
            ),
            degraded=["asr:unavailable"],
        )


_cached: ASRBackend | None = None


def _ffmpeg_present() -> bool:
    """Whisper shells out to ffmpeg for anything that is not already 16k mono
    WAV. Checking here turns an opaque CalledProcessError deep inside the
    library into a message that names the missing package."""
    return shutil.which("ffmpeg") is not None


def load_asr(model_size: str = DEFAULT_MODEL) -> ASRBackend:
    """Best available ASR backend. Cached — model load costs seconds."""
    global _cached
    if _cached is not None:
        return _cached
    for backend in (FasterWhisperBackend(model_size), OpenAIWhisperBackend(model_size)):
        if backend.available():
            _cached = backend
            return _cached
    _cached = NullASRBackend()
    return _cached


def transcribe(audio: bytes, filename: str | None = None) -> ASRResult:
    backend = load_asr()
    if isinstance(backend, NullASRBackend):
        return backend.transcribe(audio, filename)
    if not _ffmpeg_present() and not (filename or "").lower().endswith(".wav"):
        return ASRResult(
            ok=False,
            backend=backend.name,
            reason=(
                "ffmpeg is not installed, so this audio format cannot be decoded. "
                "Install ffmpeg, or upload 16kHz mono WAV, or paste the transcript."
            ),
            degraded=["asr:no_ffmpeg"],
        )
    try:
        return backend.transcribe(audio, filename)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        # A broken audio file must not 500 the request. The caller falls back
        # to asking for text, which always works.
        return ASRResult(
            ok=False,
            backend=backend.name,
            reason=f"Could not decode this audio ({type(exc).__name__}). Paste the transcript instead.",
            degraded=["asr:failed"],
        )


def status() -> dict:
    backend = load_asr()
    return {
        "backend": backend.name,
        "available": not isinstance(backend, NullASRBackend),
        "ffmpeg": _ffmpeg_present(),
    }
