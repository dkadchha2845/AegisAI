"""
C. Number-spoofing intelligence.

Extracts, per the spec: caller ID mismatch, VoIP usage, international routing,
previously reported numbers, suspicious prefixes, call frequency.

The constraint that shapes this module
--------------------------------------
Every check is structural — decidable from the number, the claimed identity,
and the call envelope alone. There is no reputation lookup and no network call,
for the same reason `engine/upi.py` has none: a blocklist this project could
ship would be stale before it was deployed, and a check the user cannot reason
about is one they are right to ignore.

That constraint is not a limitation here, it is what makes the output
defensible. "This number is +1-838, an international VoIP range, while claiming
to be Delhi Cyber Crime" is a fact the user can verify themselves. "This number
scored 0.87 on our risk model" is not.

The strongest single check
--------------------------
Caller-ID mismatch against the claimed institution. Indian agencies and banks
call from published landline ranges or registered 140-series numbers, never
from an international mobile or a VoIP gateway. The claim and the number are
independently observable, and a contradiction between them requires no
judgement call at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Indian mobile numbers are 10 digits starting 6-9. Anything else presenting
#: itself as a domestic mobile is malformed, and malformed caller ID is a
#: spoofing artefact rather than a typo when it arrives on a live call.
_INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$")

#: 140-series is the registered telemarketing/transactional block. A genuine
#: bank outbound campaign uses it; a scammer almost never does, because getting
#: one requires a registered enterprise identity.
_INDIAN_140 = re.compile(r"^140\d{7,8}$")

#: Known VoIP / virtual-number country and gateway prefixes seen in Indian
#: scam traffic. Not exhaustive by design — this flags, it does not adjudicate.
VOIP_COUNTRY_PREFIXES = {
    "1838": "US virtual (Bandwidth/Twilio range commonly resold)",
    "1938": "US virtual",
    "1206": "US virtual",
    "1929": "US virtual",
    "44744": "UK virtual mobile",
    "44793": "UK virtual mobile",
    "6531": "Singapore VoIP",
    "8562": "Laos VoIP gateway",
    "8551": "Cambodia VoIP gateway",
    "959": "Myanmar VoIP gateway",
    "2394": "Nigeria VoIP",
    "9715": "UAE virtual",
    "77": "Kazakhstan virtual range",
}

#: Country codes that are legitimate for personal international calls but are
#: never the origin of an Indian government or bank contact.
_FOREIGN_CODES = {
    "1": "United States / Canada", "44": "United Kingdom", "65": "Singapore",
    "971": "United Arab Emirates", "60": "Malaysia", "66": "Thailand",
    "856": "Laos", "855": "Cambodia", "95": "Myanmar", "234": "Nigeria",
    "7": "Russia / Kazakhstan", "212": "Morocco", "62": "Indonesia",
}

#: Institutions that only ever contact citizens from Indian numbers. Claiming
#: one of these while calling from abroad is the mismatch check.
_DOMESTIC_ONLY_CLAIMS = {
    "cbi", "police", "cyber crime", "cyber cell", "trai", "rbi", "ncb",
    "narcotics", "enforcement directorate", "income tax", "customs",
    "crime branch", "bank", "epfo", "irctc", "mha",
}

#: Real published helpline / short-code numbers. A caller presenting one of
#: these as their caller ID is spoofing a number the victim may recognise and
#: trust — a distinct and more serious signal than an unknown number.
PROTECTED_SHORT_CODES = {
    "1930": "National cybercrime helpline",
    "112": "Emergency response",
    "100": "Police",
    "139": "Railway enquiry",
    "1091": "Women's helpline",
    "14416": "Tele-MANAS mental health helpline",
}


@dataclass
class SpoofingOut:
    number: str | None = None
    confidence: float = 0.0
    band: str = "LOW"
    indicators: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    is_voip: bool | None = None
    country: str | None = None
    circle: str | None = None


def normalize_number(raw: str | None) -> tuple[str, str | None]:
    """Strip formatting and split off the country code.

    Returns (digits, country_code). An Indian number given without +91 is
    treated as domestic, which is what a local caller ID actually looks like.
    """
    if not raw:
        return "", None
    digits = re.sub(r"[^\d+]", "", str(raw))
    if digits.startswith("+"):
        digits = digits[1:]
    elif digits.startswith("00"):
        digits = digits[2:]

    if digits.startswith("91") and len(digits) >= 12:
        return digits[2:], "91"
    if len(digits) == 10 and _INDIAN_MOBILE.match(digits):
        return digits, "91"
    if digits.startswith("0") and len(digits) == 11:
        return digits[1:], "91"

    for code in sorted(_FOREIGN_CODES, key=len, reverse=True):
        if digits.startswith(code):
            return digits[len(code):], code
    return digits, None


def _voip_match(full_digits: str) -> str | None:
    for prefix, label in sorted(VOIP_COUNTRY_PREFIXES.items(), key=lambda kv: -len(kv[0])):
        if full_digits.startswith(prefix):
            return label
    return None


def analyze_number(
    number: str | None,
    *,
    claimed_identity: str | None = None,
    metadata: dict | None = None,
) -> SpoofingOut:
    """Structural spoofing assessment for one calling identity."""
    meta = metadata or {}
    out = SpoofingOut(number=number)
    if not number:
        # No caller ID at all. Not scored — absence of evidence is not
        # evidence, and inventing a risk number here would poison fusion.
        out.details.append("No caller ID was supplied, so no number checks could run.")
        return out

    raw_digits = re.sub(r"[^\d]", "", str(number))
    local, country_code = normalize_number(number)
    weights: list[float] = []

    # --- 1. Protected short-code spoofing --------------------------------
    if raw_digits in PROTECTED_SHORT_CODES:
        out.indicators.append("SHORT_CODE_SPOOF")
        out.details.append(
            f"Caller ID shows {raw_digits} ({PROTECTED_SHORT_CODES[raw_digits]}). "
            "Official helplines receive calls; they do not place them. A caller "
            "presenting this number is spoofing one you are meant to trust."
        )
        weights.append(0.95)

    # --- 2. VoIP / virtual range ------------------------------------------
    voip_label = _voip_match(raw_digits)
    if voip_label:
        out.is_voip = True
        out.indicators.append("VOIP_PREFIX")
        out.details.append(
            f"The number sits in a {voip_label} range. These are rented in bulk, "
            "are not tied to a verified identity, and are the standard carrier "
            "for organised scam operations."
        )
        weights.append(0.8)
    elif meta.get("is_voip") is True:
        out.is_voip = True
        out.indicators.append("VOIP_PREFIX")
        out.details.append("The carrier flagged this call as originating on a VoIP gateway.")
        weights.append(0.75)
    elif country_code == "91" and _INDIAN_MOBILE.match(local):
        out.is_voip = False

    # --- 3. International routing -----------------------------------------
    if country_code and country_code != "91":
        out.country = _FOREIGN_CODES.get(country_code, f"+{country_code}")
        out.indicators.append("INTERNATIONAL_ROUTING")
        out.details.append(
            f"The call is routed from {out.country} (+{country_code}), not from India."
        )
        weights.append(0.55)
    elif country_code == "91":
        out.country = "India"

    # --- 4. Caller-ID mismatch against the claimed institution -----------
    # The strongest check available, and the only one that uses the content.
    if claimed_identity:
        claim = claimed_identity.lower()
        is_domestic_claim = any(word in claim for word in _DOMESTIC_ONLY_CLAIMS)
        if is_domestic_claim and country_code and country_code != "91":
            out.indicators.append("CALLER_ID_MISMATCH")
            out.details.append(
                f"The caller claims to be {claimed_identity} but is calling from "
                f"{out.country}. No Indian agency or bank contacts citizens from "
                "an international number — this contradiction alone is decisive."
            )
            weights.append(0.95)
        elif is_domestic_claim and voip_label:
            out.indicators.append("AGENCY_NUMBER_IMPERSONATION")
            out.details.append(
                f"The caller claims to be {claimed_identity} but is calling from a "
                "virtual number. Agencies call from published landlines, and their "
                "numbers can be looked up and called back."
            )
            weights.append(0.85)
        elif is_domestic_claim and country_code == "91" and _INDIAN_MOBILE.match(local):
            # A domestic mobile is not proof of anything, but it is worth
            # saying out loud that an agency using a personal mobile is odd.
            out.indicators.append("AGENCY_NUMBER_IMPERSONATION")
            out.details.append(
                f"The caller claims to be {claimed_identity} but is calling from a "
                "personal mobile number rather than a published official line."
            )
            weights.append(0.45)

    # --- 5. Malformed / impossible number ---------------------------------
    if country_code == "91" and local and not (
        _INDIAN_MOBILE.match(local) or _INDIAN_140.match(local) or len(local) in (8, 11)
    ):
        out.indicators.append("IMPOSSIBLE_NUMBER")
        out.details.append(
            f"'{number}' is not a valid Indian number format. Malformed caller ID "
            "on a live call is an artefact of spoofing, not a typo."
        )
        weights.append(0.7)

    # --- 6. Prior complaints ----------------------------------------------
    complaints = meta.get("historical_complaints", meta.get("reported_count", 0))
    if isinstance(complaints, (int, float)) and complaints > 0:
        out.indicators.append("KNOWN_REPORTED")
        out.details.append(
            f"This number has {int(complaints)} prior fraud complaint(s) on record."
        )
        weights.append(min(0.9, 0.5 + 0.1 * float(complaints)))

    # --- 7. Call frequency -------------------------------------------------
    frequency = meta.get("call_frequency", meta.get("prior_contacts", 0))
    if isinstance(frequency, (int, float)) and frequency >= 5:
        out.indicators.append("HIGH_CALL_FREQUENCY")
        out.details.append(
            f"{int(frequency)} calls from this number in the recent window — "
            "repeated approach is characteristic of a worked target."
        )
        weights.append(0.4)

    # --- 8. Off-hours contact ---------------------------------------------
    if meta.get("off_hours"):
        out.indicators.append("OFF_HOURS_CONTACT")
        out.details.append(
            "Contact outside business hours, when no institution initiates calls "
            "and the person answering is least able to verify anything."
        )
        weights.append(0.35)

    # --- Fuse -------------------------------------------------------------
    # Noisy-OR rather than a mean. These indicators are close to independent,
    # and averaging lets a single decisive signal (an agency calling from
    # Cambodia) be diluted by the absence of unrelated ones. Noisy-OR says
    # "any one strong indicator is enough", which matches how a human analyst
    # actually reads this evidence.
    if weights:
        product = 1.0
        for w in weights:
            product *= (1.0 - w)
        out.confidence = round(1.0 - product, 3)
    out.band = _band(out.confidence)
    out.circle = _circle(local) if country_code == "91" else None
    return out


def _band(confidence: float) -> str:
    if confidence >= 0.85:
        return "CRITICAL"
    if confidence >= 0.6:
        return "HIGH"
    if confidence >= 0.3:
        return "MEDIUM"
    return "LOW"


#: Leading-digit → telecom circle. Coarse and only indicative — number
#: portability broke the strict mapping years ago — so it is reported as
#: context, never scored.
_CIRCLE_PREFIX = {
    "70": "Eastern India", "80": "Karnataka / South", "81": "South",
    "90": "North", "91": "West", "94": "South", "95": "West",
    "96": "North", "97": "West", "98": "Metro", "99": "Metro",
}


def _circle(local: str) -> str | None:
    if len(local) != 10:
        return None
    return _CIRCLE_PREFIX.get(local[:2])
