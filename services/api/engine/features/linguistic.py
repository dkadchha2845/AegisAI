"""
E. Linguistic features.

Per the spec: sentence embeddings, authority phrases, threat phrases, financial
terminology, dependency patterns.

Embeddings live in `script_templates.py`, where they do actual work against a
template library. What is left here is the part that a general NLP toolkit gets
wrong on this data: the domain phrase classes, and the syntactic shape of
coercion.

The syntactic signal is the interesting one
-------------------------------------------
Scam speech is grammatically distinctive in a way that survives paraphrase and
translation. It is overwhelmingly *imperative* ("bataiye", "kariye", "daaliye"),
*second-person* ("aapka", "aapke naam par"), and *deadline-bound* ("do ghante
mein", "aaj shaam tak"). A legitimate service call is mostly declarative and
offers optionality ("aap chahen to", "koi jaldi nahi").

That imperative-to-declarative ratio is measurable without a parser and holds
across code-mixing, which is why it is computed here directly rather than via
spaCy dependency parsing. spaCy has no Hinglish model; running its English
parser over romanised Hindi produces confident, wrong dependency trees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- Phrase classes ---------------------------------------------------------

AUTHORITY_PHRASES = [
    (r"\b(cbi|central bureau)\b", "CBI"),
    (r"\b(enforcement directorate|\bed\b)\b", "Enforcement Directorate"),
    (r"\b(ncb|narcotics control)\b", "Narcotics Control Bureau"),
    (r"\bcyber ?crime\b", "Cyber Crime cell"),
    (r"\btrai\b", "TRAI"),
    (r"\brbi\b|reserve bank", "RBI"),
    (r"\b(income tax|it department)\b", "Income Tax"),
    (r"\bcustoms\b", "Customs"),
    (r"\b(inspector|sub[- ]?inspector|acp|dcp|constable|officer)\b", "police rank"),
    (r"\bbadge (number|no)\b", "badge number"),
    (r"\b(crime branch|headquarters|nodal officer)\b", "official unit"),
    (r"\bsection \d+\b", "legal section citation"),
    (r"\b(fir|case) (number|no|id)\b", "case number"),
]

THREAT_PHRASES = [
    (r"\b(arrest|giraftar)\w*", "arrest"),
    (r"\b(warrant)\b", "warrant"),
    (r"\bnon[- ]?bailable\b", "non-bailable offence"),
    (r"\b(jail|hirasat|custody)\b", "custody"),
    (r"\b(money laundering|hawala)\b", "money laundering"),
    (r"\b(drugs|mdma|narcotics|contraband)\b", "narcotics"),
    (r"\b(freeze|seize|block ho jayega|suspend)\w*", "account action"),
    (r"\b(legal action|court|prosecution|penalty)\b", "legal consequence"),
    (r"\b(career|reputation|family).{0,20}(kharab|ruin|destroy)", "reputational threat"),
]

FINANCIAL_PHRASES = [
    (r"\b(transfer|bhej|deposit|remit)\w*", "transfer instruction"),
    (r"\b(account (number|details)|ifsc|beneficiary)\b", "account details"),
    (r"\b(upi|gpay|google pay|phonepe|paytm|bhim)\b", "UPI app"),
    (r"\b(imps|neft|rtgs)\b", "bank rail"),
    (r"\b(otp|cvv|pin|password)\b", "credential"),
    (r"\b(refundable|security deposit|escrow|supervised account)\b", "refundable framing"),
    (r"\b(court fees?|bail|fine|processing (fee|charge)|clearance)\b", "fee framing"),
    (r"\b(lakh|crore|hazaar|rupees|rs\.?|₹)\b", "amount"),
    (r"\b\d{1,3}(?:,\d{2,3})+\b", "formatted amount"),
]

URGENCY_PHRASES = [
    (r"\b(abhi|turant|immediately|right now|jaldi)\b", "immediacy"),
    (r"\b(\d+)\s*(ghante|hours?|minute|min)\b", "deadline"),
    (r"\b(aaj|today|tonight|aaj shaam|before \d)\b", "same-day deadline"),
    (r"\b(last chance|final warning|akhri)\b", "finality"),
    (r"\b(time nahi hai|no time|der ho jayegi)\b", "time pressure"),
]

#: Optionality language. This is the strongest *benign* linguistic marker in
#: the corpus — genuine institutions offer choice, scams remove it. Counted as
#: a negative weight so it can actively pull a score down rather than merely
#: failing to raise it.
OPTIONALITY_PHRASES = [
    (r"\b(koi jaldi nahi|no hurry|no rush|apne time par)\b", "explicit no-hurry"),
    (r"\b(aap chahen to|if you prefer|whenever)\b", "offered choice"),
    (r"\b(branch mein aa|visit (the |our )?branch|branch par)\w*", "branch alternative"),
    (r"\b(hum kabhi|we never|never ask)\b.{0,30}\b(otp|pin|cvv|password)\b", "credential warning"),
    (r"\b(soch (lijiye|kar|le)|think about it|call us back)\b", "deferral offered"),
]

#: Hindi imperative verb endings plus common English imperatives. The suffix
#: set is what makes this work across code-mixing.
_IMPERATIVE = re.compile(
    r"\b\w+(iye|iyega|aiye|ao|o|en)\b(?=\s|$|[,.!?])"
    r"|\b(bataiye|batao|kariye|karo|kijiye|dijiye|daaliye|bhejiye|suniye|dekhiye|"
    r"rakhiye|jaiye|likhiye|kholiye|scan|confirm|send|transfer|install|download|"
    r"press|enter|share|tell|give)\b",
    re.I,
)
_SECOND_PERSON = re.compile(r"\b(aap|aapka|aapke|aapki|aapko|tum|tumhara|your|you)\b", re.I)
_FIRST_PERSON_AUTHORITY = re.compile(r"\b(main|hum|we|i)\b.{0,25}\b(se|from)\b", re.I)
_QUESTION = re.compile(r"\?")
_SENTENCE = re.compile(r"[.!?]+")


def _hits(text: str, phrases: list[tuple[str, str]]) -> list[str]:
    return [label for pattern, label in phrases if re.search(pattern, text, re.I)]


@dataclass
class LinguisticFeatures:
    authority_hits: list[str] = field(default_factory=list)
    threat_hits: list[str] = field(default_factory=list)
    financial_hits: list[str] = field(default_factory=list)
    urgency_hits: list[str] = field(default_factory=list)
    optionality_hits: list[str] = field(default_factory=list)

    authority_density: float = 0.0
    threat_density: float = 0.0
    financial_density: float = 0.0
    urgency_density: float = 0.0
    optionality_density: float = 0.0

    imperative_ratio: float = 0.0
    second_person_ratio: float = 0.0
    question_ratio: float = 0.0
    mean_sentence_length: float = 0.0
    #: Net linguistic pressure, -1 (strongly benign) to +1 (strongly coercive).
    coercive_register: float = 0.0
    vector: list[float] = field(default_factory=list)


def extract_linguistic(text: str) -> LinguisticFeatures:
    """Linguistic feature extraction over one utterance or a whole transcript."""
    out = LinguisticFeatures()
    if not (text or "").strip():
        out.vector = [0.0] * 11
        return out

    words = re.findall(r"\w+", text)
    word_count = max(1, len(words))
    sentences = [s for s in _SENTENCE.split(text) if s.strip()] or [text]

    out.authority_hits = _hits(text, AUTHORITY_PHRASES)
    out.threat_hits = _hits(text, THREAT_PHRASES)
    out.financial_hits = _hits(text, FINANCIAL_PHRASES)
    out.urgency_hits = _hits(text, URGENCY_PHRASES)
    out.optionality_hits = _hits(text, OPTIONALITY_PHRASES)

    # Density is per-100-words and saturating. Raw counts scale with input
    # length, which would make a long benign transcript outscore a short
    # explicit threat purely on volume.
    def density(hits: list[str]) -> float:
        return round(min(1.0, len(hits) / max(1.0, word_count / 25.0)), 3)

    out.authority_density = density(out.authority_hits)
    out.threat_density = density(out.threat_hits)
    out.financial_density = density(out.financial_hits)
    out.urgency_density = density(out.urgency_hits)
    out.optionality_density = density(out.optionality_hits)

    imperatives = len(_IMPERATIVE.findall(text))
    out.imperative_ratio = round(min(1.0, imperatives / len(sentences)), 3)
    out.second_person_ratio = round(
        min(1.0, len(_SECOND_PERSON.findall(text)) / max(1.0, word_count / 12.0)), 3
    )
    out.question_ratio = round(min(1.0, len(_QUESTION.findall(text)) / len(sentences)), 3)
    out.mean_sentence_length = round(word_count / len(sentences), 2)

    # Net register. Optionality subtracts, and subtracts hard: "hum kabhi OTP
    # nahi maangte" in a message that also mentions accounts and verification
    # is the exact shape of a genuine bank call, and the regression suite in
    # tests/test_verdicts.py exists because that case used to read CRITICAL.
    positive = (
        0.30 * out.authority_density
        + 0.32 * out.threat_density
        + 0.20 * out.financial_density
        + 0.18 * out.urgency_density
    )
    negative = 0.55 * out.optionality_density
    register = positive + 0.12 * out.imperative_ratio - negative
    out.coercive_register = round(max(-1.0, min(1.0, register)), 3)

    out.vector = [
        out.authority_density,
        out.threat_density,
        out.financial_density,
        out.urgency_density,
        out.optionality_density,
        out.imperative_ratio,
        out.second_person_ratio,
        out.question_ratio,
        round(min(1.0, out.mean_sentence_length / 30.0), 3),
        1.0 if _FIRST_PERSON_AUTHORITY.search(text) else 0.0,
        round((out.coercive_register + 1.0) / 2.0, 3),
    ]
    return out
