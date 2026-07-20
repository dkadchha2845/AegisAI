"""
PRESAGE — Hinglish preservation check.

Why this module exists
----------------------
A local model asked to "reword this Hinglish, stay in Hinglish" will, most of
the time, quietly translate it into English instead. Measured on the first 21
rewrites of the corpus run: mean Hindi-marker density fell from 0.39 to 0.11,
and 76% of calls came back as clean English.

Nothing downstream catches that. The JSON parses, the line count matches, the
labels are intact — the corpus is structurally perfect and linguistically
wrong. The classifier would train on English and then meet romanised Hinglish
from the ASR at demo time, and the failure would look like "the model is just
bad" rather than "the data was translated".

So language becomes a validation gate, exactly like line count. A rewrite that
loses its Hindi is rejected and the entity-substituted version is kept, which
is always available and always correct.
"""

from __future__ import annotations

import re

# Romanised Hindi function words and high-frequency verbs. Function words are
# the right signal: they survive paraphrase (a reworded Hindi sentence still
# needs "hai", "ko", "aap") but disappear entirely under translation.
HINDI_MARKERS: set[str] = set(
    """
    hai hain tha thi the hoon ho raha rahi rahe rakhiye
    kar karo karna karne kariye kijiye dijiye jaiye bataiye batao suniye dekhiye
    aap aapka aapke aapki aapko main mera meri mere mujhe hum humara
    ka ke ki ko se mein par tak liye
    nahi nahin kya kyun kaise kaun kab kahan
    ye yeh wo voh is us isse usse
    haan han achha acha theek bilkul bas abhi phir bhi hi to
    bhai sahab sahib ji madam beta beti
    kuch koi sab sabhi lekin agar warna isliye kyunki
    padega padegi padta gaya gayi gaye hua hui hue jayega jayegi
    samajh samjha pata chalega milega dena lena
    paisa paise rupaye rupay hazaar lakh crore
    ruk ruko rukiye ghabraiye chahiye zaroori jaldi turant
    baat baate call phone number account bank
    """.split()
)

_WORD = re.compile(r"[a-z]+")


def density(text: str) -> float:
    """Fraction of word tokens that are romanised Hindi markers."""
    words = _WORD.findall(text.lower())
    if not words:
        return 0.0
    return sum(w in HINDI_MARKERS for w in words) / len(words)


def mean_density(texts: list[str]) -> float:
    if not texts:
        return 0.0
    return sum(density(t) for t in texts) / len(texts)


def preserved(
    source: list[str], rewritten: list[str], min_ratio: float = 0.70
) -> tuple[bool, float, float]:
    """
    Did the rewrite keep its Hinglish?

    Returns (ok, source_density, rewrite_density).

    The test is *relative* to the source, not an absolute floor, because the
    corpus legitimately contains English-heavy calls (the Bengaluru IT
    professional, the customer-support line). Judging those against a fixed
    threshold would reject correct rewrites; judging them against their own
    source asks the only question that matters — did this get more English
    than it started?

    A source with almost no Hindi to begin with passes trivially, which is
    correct: there was nothing to lose.
    """
    src = mean_density(source)
    out = mean_density(rewritten)
    if src < 0.05:
        return True, src, out
    return out >= src * min_ratio, src, out
