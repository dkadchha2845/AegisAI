"""
Number Spoofing Intelligence — the metadata half of a scam verdict.

A "digital arrest" call is carried as much by *how the number looks* as by what
is said on it. A real CBI officer does not cold-call from a personal +91 mobile,
a genuine Indian agency does not originate from a US or UK country code, and a
number that appears in the 1930 complaint feed is not a coincidence. This module
turns the caller's number — plus the identity they claim on the call — into the
same kind of auditable, PASS/FAIL/UNKNOWN evidence the Trust Passport produces
for the conversation.

It is deliberately mechanical, and deliberately offline (Module 1's
"Number Spoofing Intelligence": Caller-ID mismatch, VoIP usage, international
routing, previously-reported numbers, suspicious prefixes, call frequency):

  * "Does this number look shady" is not checkable.
  * "Does an Indian agency ever call from +1" is.

Like `upi.py` it ships no live reputation lookup — a blocklist a repo could bake
in is stale before the demo, and a check the user cannot reason about is one
they are right to ignore. `reported_numbers.json` is a small, clearly-synthetic
sample so the reported-number check has something to fire on; a real deployment
would sync it from the DoT/TRAI and NCRB feeds. Every FAIL still carries a
citation, and `UNKNOWN` is a real answer — a masked or absent number is not
evidence of anything and must not be scored as if it were.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..rag.store import get_kb

_DATA = Path(__file__).parent / "reported_numbers.json"


@dataclass
class SpoofCheck:
    """One named number check. Mirrors PassportCheck on the wire."""

    name: str
    verdict: str  # PASS | FAIL | UNKNOWN
    detail: str
    source: str | None = None


@dataclass
class NumberIntelOut:
    number: str | None
    risk: float          # 0-100, higher = more likely spoofed / fraudulent
    verdict: str         # PASS | FAIL | UNKNOWN — the overall call
    checks: list[SpoofCheck] = field(default_factory=list)


# Identities a caller may claim that no institution ever backs with a cold call
# from a personal mobile. Kept separate from passport.py's list because the
# question here is narrower: is this a body that would *never* call from an
# ordinary handset. Banks are intentionally excluded — a bank branch calling a
# customer from a mobile is unremarkable; the CBI doing it is not.
_AUTHORITY_CLAIM = re.compile(
    r"\b(cbi|central bureau|narcotics|ncb|enforcement directorate|\bed\b|trai|"
    r"\brbi\b|reserve bank|income tax|\bit department\b|customs|cyber ?crime|"
    r"crime branch|police|inspector|\bacp\b|\bdcp\b|\bcourt\b|\bdot\b)\b",
    re.I,
)

#: Per-check contribution to the risk score when it FAILs. Chosen so that any
#: single dispositive signal (a reported number, an international origin while
#: claiming an Indian agency) alone reads as high risk, and two soft signals
#: together also do — while a lone soft signal stays in WATCH territory.
_RISK_WEIGHT = {
    "Reported number": 60.0,
    "Caller-ID vs claimed authority": 45.0,
    "International routing": 40.0,
    "VoIP / suspicious prefix": 25.0,
    "Number format": 20.0,
    "Call frequency": 20.0,
}


def _load_data() -> dict:
    try:
        return json.loads(_DATA.read_text())
    except (OSError, json.JSONDecodeError):
        # Missing file is a degradation, not a crash — the other checks still
        # run. Matches the repo's "answer anyway, tag it" discipline.
        return {"numbers": [], "prefixes": [], "voip_prefixes": []}


_DB = _load_data()
_REPORTED = {re.sub(r"\D", "", n) for n in _DB.get("numbers", [])}
_REPORTED_PREFIXES = [re.sub(r"[^\d+]", "", p) for p in _DB.get("prefixes", [])]
_VOIP_PREFIXES = [re.sub(r"[^\d+]", "", p) for p in _DB.get("voip_prefixes", [])]


def _cite(query: str) -> str | None:
    """Best-effort knowledge-base citation, same as passport.py."""
    try:
        hits = get_kb().search(query, k=1)
    except Exception:
        return None
    return hits[0].chunk.source if hits else None


@dataclass
class _Parsed:
    raw: str
    digits: str          # pure digits (masking chars removed) — for DB matching
    masked: bool         # carrier hid part of the number (contains X)
    cc: str | None       # detected country code, "91" for India
    national: str        # number after the country code (may retain 'x' masks)
    is_intl: bool        # originates outside India


def _parse(number: str) -> _Parsed:
    raw = number.strip()
    masked = bool(re.search(r"x", raw, re.I))
    # `shape` keeps masking chars as digit placeholders so a masked number
    # still has its true length and leading series ("98XXXX1234" is a 10-digit
    # 9-series mobile). `digits` strips them for blocklist lookups, where a
    # partial match would be wrong. A leading + marks explicit international
    # form for the country-code split.
    has_plus = raw.lstrip().startswith("+")
    shape = re.sub(r"[^\dx]", "", raw, flags=re.I).lower()
    digits = shape.replace("x", "")

    cc: str | None = None
    national = shape
    if has_plus or len(shape) > 10:
        # Explicit international form, or more digits than a bare Indian mobile.
        if shape.startswith("91") and len(shape) >= 12:
            cc, national = "91", shape[2:]
        elif shape.startswith("0") and len(shape) == 11:
            cc, national = "91", shape[1:]  # domestic trunk prefix
        elif len(shape) > 10:
            # Assume the last 10 digits are the national number and whatever
            # precedes them is the country code. Correct for India (+91), the
            # NANP (+1), and most 2-digit codes — and all this check needs is
            # to tell "+91" apart from "not +91", which this does exactly.
            split = len(shape) - 10
            cc, national = shape[:split], shape[split:]
    elif len(shape) == 10:
        cc, national = "91", shape  # bare Indian number

    is_intl = cc is not None and cc != "91"
    return _Parsed(raw=raw, digits=digits, masked=masked, cc=cc,
                   national=national, is_intl=is_intl)


def _is_indian_mobile(p: _Parsed) -> bool:
    """A personal Indian mobile: 10 national digits starting 6-9."""
    return (
        (p.cc == "91" or p.cc is None)
        and len(p.national) == 10
        and p.national[0] in "6789"
    )


def analyze_number(
    number: str | None,
    *,
    claimed_identity: str | None = None,
    call_count: int = 0,
) -> NumberIntelOut:
    """Score a caller number. `claimed_identity` is the raw text the caller
    used to introduce themselves (or a resolved label); `call_count` is how
    many times this number has been seen this session."""
    if not number or not number.strip():
        return NumberIntelOut(
            number=None, risk=0.0, verdict="UNKNOWN",
            checks=[SpoofCheck(
                "Caller number", "UNKNOWN",
                "no caller number available to check",
            )],
        )

    p = _parse(number)
    claims_authority = bool(claimed_identity and _AUTHORITY_CLAIM.search(claimed_identity))
    checks: list[SpoofCheck] = []

    # 1. Reported number — dispositive on its own. Exact match, then prefix.
    if p.digits and p.digits in _REPORTED:
        checks.append(SpoofCheck(
            "Reported number", "FAIL",
            "this exact number appears in the fraud-complaint sample",
            _cite("report the fraud number on 1930 cybercrime"),
        ))
    elif any(p.digits.startswith(pref.lstrip("+"))
             for pref in _REPORTED_PREFIXES if pref):
        checks.append(SpoofCheck(
            "Reported number", "FAIL",
            "the number's prefix is associated with reported fraud campaigns",
            _cite("report the fraud number on 1930 cybercrime"),
        ))
    else:
        checks.append(SpoofCheck(
            "Reported number", "UNKNOWN",
            "not in the local complaint sample (which is illustrative, not exhaustive)",
        ))

    # 2. International routing.
    if p.is_intl:
        if claims_authority:
            checks.append(SpoofCheck(
                "International routing", "FAIL",
                f"originates outside India (+{p.cc}) while claiming an Indian agency — "
                "government bodies do not call from foreign numbers",
                _cite("scammers spoof numbers and call from international routes"),
            ))
        else:
            checks.append(SpoofCheck(
                "International routing", "UNKNOWN",
                f"originates outside India (+{p.cc}) — expected only if you know "
                "an overseas caller",
            ))
    else:
        checks.append(SpoofCheck(
            "International routing", "PASS",
            "routes through an Indian (+91) number",
        ))

    # 3. VoIP / suspicious prefix.
    voip_hit = next(
        (pref for pref in _VOIP_PREFIXES if pref and p.digits.startswith(pref.lstrip("+"))),
        None,
    )
    if voip_hit:
        checks.append(SpoofCheck(
            "VoIP / suspicious prefix", "FAIL",
            "uses an internet-telephony / bulk-calling prefix, which is how "
            "spoofed caller IDs are injected",
            _cite("VoIP internet call spoofed caller ID scam"),
        ))
    else:
        checks.append(SpoofCheck(
            "VoIP / suspicious prefix", "UNKNOWN",
            "no known VoIP/bulk prefix — this check is not exhaustive",
        ))

    # 4. Caller-ID vs claimed authority. The signature mismatch of these scams:
    #    an agency's authority delivered from an ordinary handset.
    if claims_authority:
        if _is_indian_mobile(p):
            checks.append(SpoofCheck(
                "Caller-ID vs claimed authority", "FAIL",
                "claims a government/law-enforcement identity but calls from a "
                "personal 10-digit mobile — agencies use official landlines, "
                "never a mobile handset",
                _cite("agencies do not call from personal mobile numbers"),
            ))
        elif p.is_intl:
            # Already captured by international routing; note the mismatch too.
            checks.append(SpoofCheck(
                "Caller-ID vs claimed authority", "FAIL",
                "claims an Indian agency but the number is foreign-routed",
                _cite("agencies do not call from personal mobile numbers"),
            ))
        else:
            checks.append(SpoofCheck(
                "Caller-ID vs claimed authority", "UNKNOWN",
                "claims authority; number could not be matched to an official line",
            ))
    else:
        checks.append(SpoofCheck(
            "Caller-ID vs claimed authority", "UNKNOWN",
            "no authority claimed yet — nothing to cross-check the number against",
        ))

    # 5. Number format. A number that will not parse to a plausible shape is
    #    itself a soft signal — but a *masked* number is the carrier hiding
    #    digits, not the caller, so it is UNKNOWN rather than a fault.
    if p.masked:
        checks.append(SpoofCheck(
            "Number format", "UNKNOWN",
            "partially masked by the carrier — cannot fully validate the format",
        ))
    elif p.cc is None or (p.cc == "91" and len(p.national) not in (10,) and not p.is_intl):
        checks.append(SpoofCheck(
            "Number format", "FAIL",
            "does not match a valid Indian mobile or landline format",
        ))
    else:
        checks.append(SpoofCheck(
            "Number format", "PASS",
            "parses to a well-formed number",
        ))

    # 6. Call frequency. Only meaningful with session history.
    if call_count >= 3:
        checks.append(SpoofCheck(
            "Call frequency", "FAIL",
            f"this number has driven {call_count} calls this session — repeated "
            "contact is a pressure tactic",
        ))
    else:
        checks.append(SpoofCheck(
            "Call frequency", "UNKNOWN",
            "not enough call history to judge frequency",
        ))

    # Risk = capped sum of failed-check weights. Independent evidence adds up;
    # a lone soft signal stays low. Clamped to 100.
    risk = min(100.0, sum(_RISK_WEIGHT.get(c.name, 0.0) for c in checks if c.verdict == "FAIL"))

    resolved = [c for c in checks if c.verdict != "UNKNOWN"]
    if any(c.verdict == "FAIL" for c in checks):
        verdict = "FAIL"
    elif resolved:
        verdict = "PASS"
    else:
        verdict = "UNKNOWN"

    # FAILs first, then PASS, then UNKNOWN — the reason for the risk should be
    # the top row, not buried under checks that could not run.
    order = {"FAIL": 0, "PASS": 1, "UNKNOWN": 2}
    checks.sort(key=lambda c: order[c.verdict])

    return NumberIntelOut(
        number=p.raw, risk=round(risk, 1), verdict=verdict, checks=checks
    )
