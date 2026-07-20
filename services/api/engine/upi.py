"""
UPI checks — mechanical properties of a VPA, a QR payload, or a payment request.

Everything here is a structural check on the identifier itself. That
constraint is what makes this useful: there is no reputation database, no
blocklist to go stale, and no network call in the request path. A VPA that
impersonates an institution does so in its own text, and a payment framing
that inverts the direction of money does so in its own words.

Checks return findings with a weight and a citation, and the caller turns
those into a verdict. Nothing here decides on its own — the same fusion and
provenance rules as the live path apply, because a verdict a user cannot
interrogate is one they are right to ignore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

# Registered PSP handles seen in the wild. Presence here means the suffix is a
# real PSP — it says nothing at all about whether the account is trustworthy,
# which is itself one of the findings this module emits.
KNOWN_HANDLES = {
    "oksbi", "okhdfcbank", "okicici", "okaxis", "okbizaxis",
    "ybl", "ibl", "axl", "paytm", "apl", "yapl",
    "upi", "sbi", "hdfcbank", "icici", "axisbank", "kotak", "pnb",
    "barodampay", "cnrb", "idfcbank", "indus", "federal", "jupiteraxis",
    "fbl", "airtel", "freecharge", "abfspay", "timecosmos", "waaxis",
}

#: Institution words that must never appear in the local part of a VPA a
#: citizen is asked to pay. Institutions do not collect from the public this
#: way at all, so an identifier that *claims* to be one is impersonating.
IMPERSONATION_TOKENS = [
    "rbi", "sbi", "cbi", "police", "cyber", "cybercell", "customs", "court",
    "govt", "gov", "government", "trai", "income", "incometax", "ncb",
    "narcotics", "verification", "verify", "refund", "cashback", "kyc",
    "fraud", "penalty", "fine", "challan", "legal", "bail", "escrow",
]

VPA_RE = re.compile(r"^([a-zA-Z0-9._\-]{2,256})@([a-zA-Z][a-zA-Z0-9]{1,63})$")


@dataclass
class Finding:
    label: str
    #: 0-1. How much this finding should move a verdict.
    weight: float
    detail: str
    verdict: str = "FAIL"  # FAIL | PASS | UNKNOWN
    source: str | None = None


@dataclass
class UPIAnalysis:
    vpa: str | None
    handle: str | None
    local_part: str | None
    valid_format: bool
    findings: list[Finding] = field(default_factory=list)
    #: Parsed from a `upi://pay?...` deep link or QR payload, when present.
    payee_name: str | None = None
    amount: float | None = None


def parse_upi_uri(raw: str) -> dict[str, str]:
    """Parse a `upi://pay?pa=...&pn=...&am=...` payload.

    This is what a UPI QR code actually contains, so a decoded QR and a
    pasted deep link go down the same path.
    """
    if not raw.lower().startswith("upi:"):
        return {}
    parsed = urlparse(raw)
    # urlparse puts everything after `upi://pay?` in `query` for a netloc
    # form, but bare `upi:pay?...` lands in `path`. Handle both.
    query = parsed.query or (parsed.path.split("?", 1)[1] if "?" in parsed.path else "")
    return {k: v[0] for k, v in parse_qs(query).items() if v}


def analyze_upi(raw: str, *, claimed_identity: str | None = None) -> UPIAnalysis:
    """Structural analysis of a VPA, deep link, or QR payload."""
    raw = raw.strip()
    fields = parse_upi_uri(raw)
    vpa = (fields.get("pa") or raw).strip()
    payee_name = fields.get("pn")
    amount: float | None = None
    if fields.get("am"):
        try:
            amount = float(fields["am"])
        except ValueError:
            amount = None

    match = VPA_RE.match(vpa)
    findings: list[Finding] = []

    if not match:
        return UPIAnalysis(
            vpa=vpa or None, handle=None, local_part=None, valid_format=False,
            findings=[
                Finding(
                    "Malformed UPI ID",
                    0.3,
                    "This is not a valid VPA (expected name@handle). Verify what "
                    "you were actually sent before acting on it.",
                    verdict="UNKNOWN",
                )
            ],
            payee_name=payee_name,
            amount=amount,
        )

    local, handle = match.group(1), match.group(2).lower()

    # 1. Impersonation in the local part.
    low_local = local.lower()
    hits = [tok for tok in IMPERSONATION_TOKENS if tok in low_local]
    if hits:
        findings.append(
            Finding(
                "Impersonates an institution",
                0.9,
                f"The ID contains {', '.join(sorted(set(hits))[:3])!r}. No government "
                "body or bank collects money from citizens through a UPI handle — "
                "an ID that claims to be one is impersonating.",
                source="upi-safety.md § No government body collects fines or fees by UPI to a personal VPA",
            )
        )

    # 2. Handle recognition. An unknown suffix is worth flagging but is weak
    #    evidence on its own — new PSPs launch, and this list will age.
    if handle not in KNOWN_HANDLES:
        findings.append(
            Finding(
                "Unrecognised PSP handle",
                0.25,
                f"'@{handle}' is not a PSP handle this build knows about. That is "
                "not proof of fraud, but confirm it in your own app before paying.",
                verdict="UNKNOWN",
            )
        )
    else:
        findings.append(
            Finding(
                "Handle is a real PSP",
                0.0,
                f"'@{handle}' is a registered payment provider. This says nothing "
                "about who owns the account — anyone can register a bank-branded handle.",
                verdict="PASS",
                source="upi-safety.md § Handle suffixes indicate the PSP, not legitimacy",
            )
        )

    # 3. Claimed identity vs registered payee name — the strongest signal the
    #    UPI flow offers, and only available when we have both.
    if claimed_identity and payee_name:
        inst = claimed_identity.lower().split()[0]
        if inst not in payee_name.lower():
            findings.append(
                Finding(
                    "Payee name does not match claim",
                    0.95,
                    f"The caller claims to be {claimed_identity}, but the account is "
                    f"registered to {payee_name!r}. The registered name comes from the "
                    "beneficiary bank's KYC record and cannot be faked by the payee.",
                    source="upi-safety.md § The verified payee name is the thing to read",
                )
            )
        else:
            findings.append(
                Finding(
                    "Payee name consistent with claim",
                    0.0,
                    f"Registered name {payee_name!r} is consistent with the claimed identity.",
                    verdict="PASS",
                )
            )
    elif payee_name:
        findings.append(
            Finding(
                "Registered payee",
                0.0,
                f"Account is registered to {payee_name!r}. Read this name on the "
                "confirmation screen before approving — it is bank-supplied, not payee-supplied.",
                verdict="UNKNOWN",
                source="upi-safety.md § The verified payee name is the thing to read",
            )
        )

    # 4. Personal-looking local part for an institutional claim.
    if claimed_identity and re.fullmatch(r"[6-9]\d{9}", local):
        findings.append(
            Finding(
                "Institution paying to a mobile-number VPA",
                0.7,
                "The ID is a personal mobile number. Institutions do not collect "
                "official payments into a personal number's VPA.",
                source="upi-safety.md § No government body collects fines or fees by UPI to a personal VPA",
            )
        )

    # 5. A pre-filled amount in a QR is normal for a merchant and abnormal for
    #    a "refund" — flagged only in combination, which the caller does.
    if amount is not None:
        findings.append(
            Finding(
                "Pre-filled amount",
                0.15,
                f"This code will send ₹{amount:,.0f} out of your account. Scanning a "
                "QR code always sends money — it never receives.",
                verdict="UNKNOWN",
                source="upi-safety.md § Scanning a QR code sends money, it does not receive it",
            )
        )

    return UPIAnalysis(
        vpa=vpa, handle=handle, local_part=local, valid_format=True,
        findings=findings, payee_name=payee_name, amount=amount,
    )


# ---------------------------------------------------------------------------
# Payment-framing checks over free text
# ---------------------------------------------------------------------------

FRAMING_RULES: list[tuple[str, str, float, str, str]] = [
    (
        r"\b(pin|upi pin|mpin)\b.*\b(receive|refund|cashback|paisa aayega|credit)\b"
        r"|\b(receive|refund|cashback)\b.*\b(pin|upi pin)\b",
        "PIN requested to receive money",
        1.0,
        "A UPI PIN only ever authorises money leaving your account. Being asked "
        "for one 'to receive' a refund means the transfer is outgoing.",
        "upi-safety.md § Receiving money never requires a PIN",
    ),
    (
        r"\b(scan|qr)\b.*\b(receive|refund|cashback|paisa milega)\b",
        "QR scan framed as receiving",
        1.0,
        "Scanning a UPI QR always sends money. A QR presented as the way to "
        "receive a refund is a payment request in disguise.",
        "upi-safety.md § Scanning a QR code sends money, it does not receive it",
    ),
    (
        r"\bcollect request\b|\brequest (approve|accept) k\w+\b",
        "Collect request",
        0.7,
        "A collect request asks you to approve an outgoing payment. The 'refund' "
        "or 'verification' text in the remarks is written by whoever sent it.",
        "upi-safety.md § Collect requests are pull payments",
    ),
    (
        r"\b(imps|neft|rtgs)\b.*\b(instead|nahi ho raha|try kar)\w*|\blimit\b.*\b(split|do baar|alag)\w*",
        "Switching rails after a failure",
        0.6,
        "Moving to a different payment rail or splitting the amount after a "
        "failure is a way around transaction limits. It means the amount matters "
        "more to the caller than the method.",
        "upi-safety.md § Transaction limits shape the script",
    ),
    (
        r"\b(refundable|security deposit|escrow|supervised account|verification (ke liye|charge))\b",
        "Refundable-deposit framing",
        0.85,
        "Money sent to prove innocence or unlock a refund is never returned. No "
        "real process asks you to send funds to verify that you have them.",
        "rbi-advisories.md § Money is never seized by asking the owner to send it",
    ),
]

_FRAMING = [(re.compile(p, re.I), *rest) for p, *rest in FRAMING_RULES]


def analyze_payment_framing(text: str) -> list[Finding]:
    """Findings about how a payment is being *described*, independent of any
    identifier. This is what catches a scam that has not named a VPA yet."""
    out: list[Finding] = []
    for pattern, label, weight, detail, source in _FRAMING:
        if pattern.search(text):
            out.append(Finding(label, weight, detail, source=source))
    return out
