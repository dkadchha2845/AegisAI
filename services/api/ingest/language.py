"""
Language detection.

    fastText lid.176  → preferred when the model file is present.
    marker heuristic  → always available, and genuinely better on this data.

The heuristic is not a token fallback here, and that is worth stating plainly.
Off-the-shelf detectors are trained on monolingual documents and consistently
label romanised Hinglish as English, Indonesian, or Malay — the two Latin-script
languages with similar function-word shapes. `ml/aegis/hinglish.py` already
proved this empirically inside this project: a model asked to preserve Hinglish
translated 76% of a corpus to English while every structural check still passed.

So the local detector measures romanised-Hindi function-word density directly,
reusing that same marker set. Function words are the right signal because they
survive paraphrase — a reworded Hindi sentence still needs "hai", "ko", "aap" —
but vanish entirely under translation. For this input distribution that beats a
general-purpose classifier, so it is the default rather than the fallback.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from ..config import ML_DIR

# Reuse the marker set that the dataset pipeline already validated against.
sys.path.insert(0, str(ML_DIR))
try:
    from aegis.hinglish import HINDI_MARKERS, density  # type: ignore
except ImportError:  # pragma: no cover - ml/ absent in a container build
    HINDI_MARKERS = {
        "hai", "hain", "aap", "aapka", "ko", "se", "mein", "nahi", "kya",
        "main", "mera", "karo", "kar", "ji", "haan", "theek", "bhej", "paisa",
    }

    def density(text: str) -> float:  # type: ignore[misc]
        words = re.findall(r"[a-z]+", text.lower())
        if not words:
            return 0.0
        return sum(w in HINDI_MARKERS for w in words) / len(words)


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")

#: Above this romanised-Hindi density a message is code-mixed rather than
#: English. Chosen from the corpus: benign English-heavy calls in the gold set
#: sit at 0.02-0.06, Hinglish calls at 0.25-0.45, so the gap is wide and the
#: exact cut is not load-bearing.
HINGLISH_FLOOR = 0.10
HINDI_HEAVY_FLOOR = 0.32


@dataclass
class LanguageResult:
    #: BCP-47-ish tag. `hi-Latn` is the honest label for romanised Hindi and is
    #: what the rest of the pipeline branches on.
    language: str
    confidence: float
    script: str  # latin | devanagari | mixed
    hindi_marker_density: float
    backend: str
    degraded: list[str]


def _fasttext_model_path() -> Path | None:
    candidate = ML_DIR / "artifacts" / "lid.176.ftz"
    return candidate if candidate.exists() else None


def _detect_fasttext(text: str) -> LanguageResult | None:
    path = _fasttext_model_path()
    if path is None:
        return None
    try:
        import fasttext  # type: ignore

        model = fasttext.load_model(str(path))
        labels, probs = model.predict(text.replace("\n", " "), k=1)
        lang = labels[0].replace("__label__", "")
        return LanguageResult(
            language=lang,
            confidence=float(probs[0]),
            script="devanagari" if _DEVANAGARI.search(text) else "latin",
            hindi_marker_density=density(text),
            backend="fasttext",
            degraded=[],
        )
    except (ImportError, ValueError, OSError):
        return None


def detect(text: str) -> LanguageResult:
    """Detect the language of an utterance or a whole transcript."""
    stripped = (text or "").strip()
    if not stripped:
        return LanguageResult("und", 0.0, "latin", 0.0, "heuristic", ["lang:empty"])

    has_deva = bool(_DEVANAGARI.search(stripped))
    marker_density = density(stripped)

    # Devanagari is unambiguous — no detector needed, and no detector does
    # better than reading the codepoints.
    if has_deva:
        latin_words = len(re.findall(r"[a-zA-Z]{2,}", stripped))
        script = "mixed" if latin_words > 2 else "devanagari"
        return LanguageResult("hi", 0.98, script, marker_density, "script", [])

    ft = _detect_fasttext(stripped)
    if ft is not None:
        # Even with fastText available, override its answer when the marker
        # density says code-mixed. This is the failure mode described in the
        # module docstring, and the override is the entire reason the density
        # is computed at all.
        if marker_density >= HINGLISH_FLOOR and ft.language in {"en", "id", "ms", "tl"}:
            ft.language = "hi-Latn"
            ft.confidence = min(0.95, 0.55 + marker_density)
            ft.degraded = ["lang:heuristic_override"]
        return ft

    if marker_density >= HINDI_HEAVY_FLOOR:
        return LanguageResult("hi-Latn", min(0.95, 0.6 + marker_density), "latin",
                              marker_density, "heuristic", [])
    if marker_density >= HINGLISH_FLOOR:
        return LanguageResult("hi-Latn", 0.6 + marker_density, "latin",
                              marker_density, "heuristic", [])
    return LanguageResult("en", 0.75, "latin", marker_density, "heuristic", [])


def is_supported(result: LanguageResult) -> bool:
    """The classifier is trained on Hinglish and Indian English only.

    Anything else gets flagged rather than scored: MuRIL will happily return a
    confident label for Tamil or Bengali text it has no business labelling, and
    a confident wrong stage is worse than an honest "out of scope".
    """
    return result.language in {"hi", "hi-Latn", "en", "und"}


def status() -> dict:
    return {
        "backend": "fasttext" if _fasttext_model_path() else "heuristic",
        "supported": ["hi", "hi-Latn", "en"],
    }
