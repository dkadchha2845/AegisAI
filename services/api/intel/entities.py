"""
Fraud entity extraction (FIGAE / Module 2, Step 2).

Every scam case — whether a historical record or a live Module 1 detection — is
reduced to the same flat set of entities so the knowledge graph can connect them.
The taxonomy is the PDF's: communication (phone, email, domain), financial (UPI,
wallet, bank account, amount), scam intelligence (scam type, fake authority,
script template), and location (city / district / state).

Extraction is mechanical and offline, exactly like `engine/spoofing.py` and
`engine/upi.py`: regexes over text, plus structured fields lifted straight from a
Module 1 evidence package when one is available. Nothing is inferred that cannot
be pointed at — an entity the graph draws an edge from has to be a substring a
human can find in the source, because a fraud-network link submitted as evidence
is only as good as its provenance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# --- patterns ---------------------------------------------------------------
# Deliberately conservative. A false entity is a false edge, and a false edge is
# a fraud-network link that does not exist — the one thing an "intelligence
# package for legal admissibility" cannot afford.

_PHONE = re.compile(r"(?:(?:\+|00)?91[\-\s]?)?[6-9]\d{9}\b")
_UPI = re.compile(r"\b[a-zA-Z0-9._\-]{2,64}@[a-zA-Z][a-zA-Z0-9]{1,32}\b")
_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_WALLET = re.compile(r"\b(?:0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
_BANK_ACCT = re.compile(r"\b\d{9,18}\b")
_DOMAIN = re.compile(r"\b(?:https?://)?((?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,})(?:/\S*)?")
_AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr)\s?([\d,]+(?:\.\d+)?)|([\d,]{4,})\s?(?:rupees|rs\b)", re.I
)

# UPI handles share the shape of email local parts; a handle with a dotted or
# well-known consumer-mail suffix is an email, not a VPA. Same discriminator as
# engine/analyzer.py::extract_upi_ids so the two never disagree.
_EMAIL_SUFFIXES = {"gmail", "yahoo", "outlook", "hotmail", "icloud", "proton", "rediffmail"}

_AUTHORITY = re.compile(
    r"\b(cbi|central bureau|narcotics|ncb|enforcement directorate|\bed\b|trai|"
    r"\brbi\b|reserve bank|income tax|customs|cyber ?crime|crime branch|police|"
    r"\bfedex\b|\bdhl\b|blue ?dart|epfo|\buidai\b|aadhaar|customer care)\b",
    re.I,
)

# Bank names a scammer poses as, or names as the destination for a transfer.
# Display context, not a graph edge — two cases both naming "SBI" are not linked
# by that alone, so this never feeds iter_case_entities.
_BANK_NAMES = re.compile(
    r"\b(state bank of india|\bsbi\b|hdfc(?: bank)?|icici(?: bank)?|axis bank|"
    r"kotak(?: mahindra)?|punjab national bank|\bpnb\b|bank of baroda|\bbob\b|"
    r"canara bank|union bank|yes bank|\bidfc\b|indusind|federal bank|"
    r"paytm payments bank|india post payments)\b",
    re.I,
)

# Account numbers only when explicitly labelled — a bare 9-18 digit run also
# matches phone numbers, Aadhaar, and case IDs, so we require an "A/C" cue.
_BANK_ACCT_LABELLED = re.compile(
    r"(?:a\/?c(?:count)?(?:\s*(?:no\.?|number|#))?)\s*[:\-]?\s*(\d{9,18})\b", re.I
)

# Scam-intelligence keywords — what kind of scam this is, in the words that
# appear on the artifact. Ordered longest-first so "digital arrest" wins over a
# bare "arrest".
_SCAM_KEYWORDS = [
    "digital arrest", "money laundering", "work from home", "gift card",
    "customs duty", "electricity bill", "sim swap", "lottery", "otp", "kyc",
    "pan card", "aadhaar", "warrant", "parcel", "courier", "refund", "customs",
    "loan", "investment", "trading", "blackmail", "bitcoin", "cryptocurrency",
    "gift voucher", "insurance", "job offer", "part time",
]
_SCAM_KEYWORDS_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _SCAM_KEYWORDS) + r")\b", re.I
)


@dataclass
class ExtractedEntities:
    """The flat entity set for one fraud case. Lists, because one case can name
    several numbers or VPAs — a mule ring's whole point is more than one."""

    phones: List[str] = field(default_factory=list)
    upi_ids: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    wallets: List[str] = field(default_factory=list)
    bank_accounts: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    amounts: List[float] = field(default_factory=list)
    authorities: List[str] = field(default_factory=list)
    #: Display-only context (never graph edges): the bank a caller names, the
    #: places mentioned, and the scam-type keywords on the artifact.
    banks: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    scam_keywords: List[str] = field(default_factory=list)

    def merge(self, other: "ExtractedEntities") -> None:
        for f in (
            "phones", "upi_ids", "emails", "wallets", "bank_accounts",
            "domains", "authorities", "banks", "locations", "scam_keywords",
        ):
            seen = getattr(self, f)
            for v in getattr(other, f):
                if v not in seen:
                    seen.append(v)
        self.amounts.extend(other.amounts)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "phones": self.phones,
            "upi_ids": self.upi_ids,
            "emails": self.emails,
            "wallets": self.wallets,
            "bank_accounts": self.bank_accounts,
            "domains": self.domains,
            "amounts": self.amounts,
            "authorities": self.authorities,
            "banks": self.banks,
            "locations": self.locations,
            "scam_keywords": self.scam_keywords,
        }


def _norm_phone(raw: str) -> str:
    """Last 10 digits — the national number. Collapses +91/0/spacing variants of
    one number to a single node so the graph does not split a mule across three
    spellings of the same handset."""
    digits = re.sub(r"\D", "", raw)
    return digits[-10:] if len(digits) >= 10 else digits


def extract_from_text(text: str) -> ExtractedEntities:
    """Pull every entity out of a blob of free text (a transcript, an SMS)."""
    out = ExtractedEntities()
    if not text:
        return out

    for m in _PHONE.findall(text):
        n = _norm_phone(m)
        if len(n) == 10 and n not in out.phones:
            out.phones.append(n)

    # Emails FIRST, keeping their character spans. A full email like
    # `cbi.helpdesk@gov-in-portal.com` must be claimed before the looser UPI and
    # domain patterns run, or the UPI pattern grabs the fragment `…@gov` and the
    # domain pattern lists the local part `cbi.helpdesk` as a website.
    email_spans: List[tuple[int, int]] = []
    for m in _EMAIL.finditer(text):
        tok = m.group(0)
        email_spans.append((m.start(), m.end()))
        if tok not in out.emails:
            out.emails.append(tok)

    def _in_email(s: int, e: int) -> bool:
        return any(s >= es and e <= ee for es, ee in email_spans)

    # UPI: @-tokens that are not part of an email. A trailing "-" or "." means
    # the match stopped inside a longer email/domain, so it is a fragment.
    for m in _UPI.finditer(text):
        s, e, tok = m.start(), m.end(), m.group(0)
        if _in_email(s, e) or text[e : e + 1] in "-.":
            continue
        suffix = tok.split("@", 1)[1].lower()
        if suffix in _EMAIL_SUFFIXES:
            if tok not in out.emails:
                out.emails.append(tok)
        elif tok not in out.upi_ids:
            out.upi_ids.append(tok)

    for w in _WALLET.findall(text):
        if w not in out.wallets:
            out.wallets.append(w)

    # Domains: skip local parts (a "domain" immediately followed by "@") and
    # anything already inside a captured email — the email's own domain is not a
    # separate website the citizen was sent to.
    for m in _DOMAIN.finditer(text):
        d = m.group(1).lower().rstrip(".")
        end = m.end(1)
        if text[end : end + 1] == "@" or _in_email(m.start(1), end):
            continue
        if "." in d and d not in out.domains and not d.replace(".", "").isdigit():
            out.domains.append(d)

    for m in _BANK_ACCT_LABELLED.finditer(text):
        acct = m.group(1)
        if acct not in out.bank_accounts:
            out.bank_accounts.append(acct)

    for a, b in _AMOUNT.findall(text):
        raw = (a or b).replace(",", "")
        try:
            val = float(raw)
            if val >= 100:  # sub-₹100 "amounts" are usually years or counts
                out.amounts.append(val)
        except ValueError:
            pass

    for auth in _AUTHORITY.findall(text):
        label = auth.strip().lower()
        if label and label not in out.authorities:
            out.authorities.append(label)

    for bank in _BANK_NAMES.findall(text):
        label = (bank[0] if isinstance(bank, tuple) else bank).strip().lower()
        if label and label not in out.banks:
            out.banks.append(label)

    for kw in _SCAM_KEYWORDS_RE.findall(text):
        label = kw.strip().lower()
        if label and label not in out.scam_keywords:
            out.scam_keywords.append(label)

    # Locations — matched against the same gazetteer the map uses, so "fraud near
    # you" and "places named on the call" speak of the same cities. Lazy import
    # keeps this module free of a load-time dependency on geo.
    try:
        from .geo import CITIES

        low = text.lower()
        for city in CITIES:
            if re.search(r"\b" + re.escape(city.lower()) + r"\b", low) and city not in out.locations:
                out.locations.append(city)
    except Exception:  # noqa: BLE001 - geo optional; locations are display-only
        pass

    return out


def extract_from_package(package: Dict[str, Any]) -> ExtractedEntities:
    """Lift entities from a Module 1 evidence package.

    Prefers the package's already-structured fields (caller number, claimed
    identity, UPI payload) over re-parsing prose, then tops up from the
    transcript so nothing said on the call is missed. This is the bridge the PDF
    calls 'Source 2 — Real-Time Intelligence from Module 1': every scam Module 1
    detects becomes structured intelligence in the repository.
    """
    out = ExtractedEntities()

    call = package.get("call", {}) or {}
    if call.get("caller_number"):
        n = _norm_phone(str(call["caller_number"]))
        if n:
            out.phones.append(n)

    assess = package.get("assessment", {}) or {}
    if assess.get("claimed_identity"):
        out.merge(_authority_only(str(assess["claimed_identity"])))

    # Transcript is the richest source of VPAs/amounts spoken mid-call.
    for turn in package.get("transcript", []) or []:
        out.merge(extract_from_text(str(turn.get("text", ""))))

    return out


def _authority_only(text: str) -> ExtractedEntities:
    out = ExtractedEntities()
    for auth in _AUTHORITY.findall(text or ""):
        label = auth.strip().lower()
        if label and label not in out.authorities:
            out.authorities.append(label)
    return out


def entity_key(kind: str, value: str) -> str:
    """Stable node id for the graph: `phone:98…`, `upi:x@y`. One key per real
    entity so two cases naming the same number land on the same node."""
    return f"{kind}:{value.strip().lower()}"


def iter_case_entities(case: Dict[str, Any]) -> Iterable[tuple[str, str]]:
    """Yield (kind, value) pairs for every shareable entity on a case dict.
    `amounts` and free-text are intentionally excluded — an amount is evidence
    of loss, not a shared identifier two cases can be linked through."""
    for kind, field_name in (
        ("phone", "phones"),
        ("upi", "upi_ids"),
        ("email", "emails"),
        ("wallet", "wallets"),
        ("bank", "bank_accounts"),
        ("domain", "domains"),
    ):
        for v in case.get(field_name, []) or []:
            if v:
                yield kind, str(v)
