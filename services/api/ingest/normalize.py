"""
Text cleaning and normalisation.

Sits between "raw text from ASR, OCR, or a paste" and the feature extractors.
The whole job is to remove things that are noise for classification while
preserving everything that is signal — and on this data the line between those
two is not where a general-purpose NLP cleaner would put it.

Four things are deliberately NOT normalised away
------------------------------------------------
**Digits.** `ml/corpus/build_dataset.py` already learned this the hard way: stripping
numbers collapses "amount daaliye 450000" and "amount daaliye 250000" into one
key and deletes most of PAYMENT_EXECUTION from the corpus. Amounts, case IDs
and account numbers are the most scam-specific tokens in the entire input.

**Repetition.** "haan haan haan" is a compliance signal and "bataiye, bataiye"
is escalating pressure. A deduplicating cleaner erases the behavioural layer.

**Case.** Not lowercased here. MuRIL is a cased model, and "CBI" versus "cbi"
carries real information about whether an acronym was spoken as an institution.
The lexical classifier compiles its own patterns with re.I, so it is unaffected.

**Hinglish spelling variants.** "kijiye"/"kijie"/"kijiy" are collapsed only
through an explicit, short map. A general stemmer trained on English mangles
romanised Hindi — "mein" becomes "mein", but "bataiye" becomes "batai" — and
the markers those extractors depend on stop matching.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: ASR artefacts and transcription noise that carry no meaning.
_FILLER_TAGS = re.compile(r"\[(inaudible|silence|music|noise|laughter|crosstalk)\]", re.I)
_SPEAKER_PREFIX = re.compile(
    r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?"
    r"(caller|scammer|agent|victim|me|you|user|customer|unknown|speaker ?\d+)"
    r"\s*[:\-–—]\s*",
    re.I,
)
_URL = re.compile(r"https?://\S+|www\.\S+")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_PUNCT = re.compile(r"([!?.,])\1{2,}")

#: Romanised-Hindi spelling variants that genuinely mean the same token. Kept
#: short and explicit on purpose — every entry is a decision, not a rule.
_VARIANTS = {
    "kijie": "kijiye", "kijiy": "kijiye", "keejiye": "kijiye",
    "batayiye": "bataiye", "bataiy": "bataiye", "bataye": "bataiye",
    "nahin": "nahi", "nhi": "nahi",
    "haa": "haan", "han": "haan", "haanji": "haan ji",
    "thik": "theek", "theak": "theek", "tk": "theek",
    "aadhar": "aadhaar", "adhaar": "aadhaar", "adhar": "aadhaar",
    "paise": "paisa", "rupaye": "rupees", "rupay": "rupees",
    "ghanta": "ghante", "ghnte": "ghante",
    "kripya": "kripaya",
    "pls": "please", "plz": "please", "pleej": "please",
}
_VARIANT_RE = re.compile(
    r"\b(" + "|".join(sorted(_VARIANTS, key=len, reverse=True)) + r")\b", re.I
)

#: Spoken-number words that appear in amounts. ASR frequently emits these in
#: words rather than digits, and the payment extractors match on digits.
_SPOKEN_AMOUNTS = {
    "lakh": "00000", "lakhs": "00000", "lac": "00000",
    "crore": "0000000", "crores": "0000000",
    "hazaar": "000", "hazar": "000", "thousand": "000",
}


@dataclass
class NormalizedText:
    text: str
    #: What was stripped, for audit. A cleaner that silently eats content is
    #: impossible to debug when a verdict comes out wrong.
    removed: list[str]
    had_speaker_prefix: bool


def strip_speaker_prefix(line: str) -> tuple[str, bool]:
    """Remove a leading `Caller:` / `[00:12] AGENT —` marker if present."""
    match = _SPEAKER_PREFIX.match(line)
    if not match:
        return line.strip(), False
    return line[match.end():].strip(), True


def normalize_amounts(text: str) -> str:
    """Turn "4 lakh 50 hazaar" into something the amount regexes can see.

    Runs before digit-preserving cleanup because ASR output says amounts in
    words far more often than a typed message does, and `engine/upi.py` plus
    the payment-stage cues both key off numeric forms.
    """
    def repl(match: re.Match) -> str:
        value, unit = match.group(1), match.group(2).lower()
        zeros = _SPOKEN_AMOUNTS.get(unit, "")
        return f"{value}{zeros}" if zeros else match.group(0)

    pattern = r"\b(\d+(?:\.\d+)?)\s*(" + "|".join(_SPOKEN_AMOUNTS) + r")\b"
    return re.sub(pattern, repl, text, flags=re.I)


def normalize(text: str, *, strip_prefix: bool = True) -> NormalizedText:
    """Clean one utterance. Idempotent — normalising twice changes nothing."""
    removed: list[str] = []
    original = text or ""

    # Unicode NFKC first: ASR and OCR both emit full-width digits, curly
    # quotes, and non-breaking spaces that otherwise break every regex written
    # against the ASCII forms.
    out = unicodedata.normalize("NFKC", original)
    out = out.replace("​", "").replace("﻿", "")

    had_prefix = False
    if strip_prefix:
        out, had_prefix = strip_speaker_prefix(out)

    if _FILLER_TAGS.search(out):
        removed.append("filler_tags")
        out = _FILLER_TAGS.sub(" ", out)

    if _URL.search(out):
        # Replaced rather than deleted: the *presence* of a link in a scam
        # message is itself a signal, so the extractors need to see that one
        # was there without the raw domain skewing the embeddings.
        removed.append("urls")
        out = _URL.sub(" <link> ", out)

    out = normalize_amounts(out)
    out = _VARIANT_RE.sub(lambda m: _VARIANTS[m.group(0).lower()], out)
    out = _MULTI_PUNCT.sub(r"\1", out)
    out = _MULTI_SPACE.sub(" ", out)
    return NormalizedText(text=out.strip(), removed=removed, had_speaker_prefix=had_prefix)


def normalize_many(lines: list[str]) -> list[str]:
    cleaned = [normalize(line).text for line in lines]
    return [line for line in cleaned if line]


def split_utterances(blob: str) -> list[str]:
    """Split a pasted block into utterances.

    Newlines win when present, because that is how transcripts are actually
    formatted. Sentence splitting is the fallback for a single-paragraph SMS,
    and is deliberately conservative — over-splitting an SMS into six fragments
    gives the classifier six low-information inputs instead of one good one.
    """
    lines = [line.strip() for line in (blob or "").splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    single = lines[0] if lines else ""
    if len(single) < 180:
        return [single] if single else []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Zऀ-ॿ])", single)
    return [p.strip() for p in parts if p.strip()]
