"""
Trust Passport — checks a caller's claimed identity against what institutions
actually do.

Each check returns PASS, FAIL, or UNKNOWN, and every non-UNKNOWN verdict
carries the knowledge-base document that backed it. UNKNOWN is a real answer
here, not a failure mode: a check that has not yet had the evidence to run
must not be counted as passed, and must not be counted as failed either. The
trust percentage is computed over resolved checks only, so a passport with one
FAIL out of one resolved check reads 0% rather than being diluted by six
checks that never ran.

The checks are deliberately mechanical. "Does this caller sound suspicious" is
not checkable; "did this caller ask for an OTP" is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..rag.store import get_kb


@dataclass
class CheckOut:
    name: str
    verdict: str  # PASS | FAIL | UNKNOWN
    detail: str
    source: str | None = None


@dataclass
class PassportOut:
    claimed_identity: str | None
    final_trust_pct: float
    checks: list[CheckOut] = field(default_factory=list)


# Institution names a caller may claim. Order matters: the first match wins,
# and the more specific patterns are listed first.
IDENTITY_PATTERNS: list[tuple[str, str]] = [
    (r"\bcyber ?crime\b", "Cyber Crime cell"),
    (r"\b(cbi|central bureau)\b", "CBI"),
    (r"\b(narcotics|ncb)\b", "Narcotics Control Bureau"),
    (r"\b(enforcement directorate|\bed\b)\b", "Enforcement Directorate"),
    (r"\btrai\b", "TRAI"),
    (r"\brbi\b|reserve bank", "RBI"),
    (r"\b(income tax|it department)\b", "Income Tax Department"),
    (r"\b(customs|courier|fedex|dhl|blue ?dart)\b", "Courier / Customs"),
    (r"\b(police|inspector|acp|dcp|thana)\b", "Police"),
    (r"\b(bank|fraud cell|customer care)\b", "Bank"),
]


_CREDENTIAL = re.compile(r"\b(otp|cvv|upi pin|atm pin|pin|password)\b", re.I)

#: Contexts in which a credential is *named* rather than *requested*: the
#: warning form ("we never ask for your OTP") and the refusal form ("I won't
#: give you the OTP"). Both mention the credential without anyone asking for
#: it, and matching the bare word flagged a real bank reminder call as
#: CRITICAL — the exact false positive that teaches users to ignore alerts.
_CREDENTIAL_ADVISORY = re.compile(
    r"(kabhi|never|nahi|not|don'?t|do not|mat)\s+\w*\s*"
    r"(mang|maang|pooch|puch|ask|share|batao|bataye|bataenge|give|denge|dunga|dungi)"
    r"|(mang|maang|ask|share|batao|bataye)\w*\s+(nahi|mat|never)"
    r"|\bnever share\b|\bdo not share\b"
    # The Hinglish warning puts the refusal after the credential: "koi OTP mat
    # dena", "maange toh mat dijiyega", "OTP ya card details nahi chahiye".
    # Each read as a request until audit B-08's call-level run found five
    # genuine bank and support calls scored 95 on exactly these lines.
    r"|\b(mat|nahi|never)\s+(dena|dijiye\w*|dein|do|batana|bataiye\w*|chahiye)\b",
    re.I,
)

#: A credential being *delivered* rather than requested: the bank's own SMS
#: states the code ("Your OTP for login is 482913"), and a delivery agent at the
#: door asks to be *shown* one. Neither can be done to a caller on the phone,
#: which is the only place this check matters.
_CREDENTIAL_DELIVERY = re.compile(
    r"\b(otp|code|pin)\b[^.?!]{0,25}\bis\s*:?\s*\d{4,8}\b|\b(otp|code)\b[^.?!]{0,10}\bdikha\w*",
    re.I,
)

#: How far either side of the credential word the advisory framing has to sit
#: to count. Whole-utterance matching would let "kisi ko mat bataiye" — the
#: isolation line — suppress a genuine "OTP bataiye" in the same breath, which
#: is a failure in the dangerous direction.
_ADVISORY_WINDOW = 45


def _is_credential_request(text: str) -> bool:
    """True if a credential is being asked for, rather than warned about."""
    if _CREDENTIAL_DELIVERY.search(text):
        return False
    for match in _CREDENTIAL.finditer(text):
        start = max(0, match.start() - _ADVISORY_WINDOW)
        window = text[start : match.end() + _ADVISORY_WINDOW]
        if not _CREDENTIAL_ADVISORY.search(window):
            return True
    return False


#: Secrecy as a *demand*. The bare word "confidential" fired on "NetBank will
#: never ask for your confidential details" — a bank warning — and floored a
#: genuine call at 91 (audit B-08). The Hinglish forms are already imperatives.
_SECRECY = re.compile(
    r"\b(kisi ko (mat|nahi)|disconnect mat|digital arrest|akele)\b"
    r"|\b(this|the|yeh|ye) (matter|call|case|investigation|conversation) is "
    r"(strictly |highly )?(confidential|classified|secret)\b"
    r"|\b(keep|kept) (this|it|everything) (strictly )?(confidential|secret|between us)\b"
    r"|\b(confidential|gopniya) (hai|rakh)\w*"
    r"|\b(do not|don'?t|must not) (tell|inform) (anyone|anybody|your family)\b",
)

#: The same word in a warning: "we will never ask for your confidential details".
_SECRECY_ADVISORY = re.compile(r"\bnever ask\w* (you )?for (your )?confidential\b")

#: Money asked for in the shape only a scam uses: an account that is "safe",
#: "supervised" or the regulator's, a deposit that is "refundable", a payment
#: that proves innocence. The old pattern matched the bare verbs transfer,
#: bhej and deposit, and floored at 87 a call transfer, a fixed deposit, a
#: refund timeline and a mother asking her son to send money (audit B-08).
#: A plain request to pay still reaches the score through the payment stage —
#: it is just no longer conclusive on its own.
_SCAM_PAYMENT = re.compile(
    r"\b(escrow|supervised account|security deposit|refundable (deposit|fee|amount|charge))\b"
    r"|\b(safe|surakshit|secure|verification|rbi|government|sarkari) (custody )?(account|khaate|khata)\b"
    r"|\bcustody account\b"
    # Advance fee: money demanded before a prize, a withdrawal or a refund is
    # released. A real payout deducts its tax; it never asks for it first.
    r"|\bpre-?deposit\b"
    r"|\b(to (release|unlock|claim|withdraw)|before (you can )?(withdraw|release))\b[^.?!]{0,50}"
    r"\b(pay|deposit|fee|tax|charge)\w*"
    r"|\b(withdraw\w*|release|nikaal\w*) (se|karne se) pehle\b[^.?!]{0,60}\b(tax|fee|charge|deposit|pay)\w*"
    r"|\b(prove|clear) (your )?(innocence|name)\b|\bnaam clear\b"
    r"|\b(paise|paisa|amount|funds?|money|rupees|rs\.?|₹|\d{4,})\b[^.?!]{0,40}"
    r"\b(rbi|government|sarkari) (ke )?(account|khaate|khata|mein)\b",
)

#: Payment demanded on pain of arrest. Kept to *criminal* consequences on
#: purpose: a real e-challan says "pay within 60 days or it goes to the virtual
#: court", and a real tax notice threatens "legal action" — neither threatens
#: to arrest you unless you pay now, which no agency does.
_PAY_VERB = r"\b(pay|transfer|deposit|send|clear|bhej\w*|jama kar\w*|bhar\w*|transfer kar\w*)\b"
_THREAT = (
    r"\b(arrest\w*|police (case|complaint)|fir\b|warrant|jail|giraftar\w*|"
    r"case (will be |hoga |ho jayega )?(filed|registered|darj))"
)
#: Within one sentence. A "." inside a token — `fedex.customs@okaxis`, "Rs.",
#: "4,999.00" — is not the end of one, and stopping there let "pay … to
#: fedex.customs@okaxis or a police case will be filed" through.
_SAME_SENTENCE = r"(?:[^.?!]|\.(?=\S))"
_PAYMENT_UNDER_THREAT = re.compile(
    _PAY_VERB + _SAME_SENTENCE + r"{0,80}?\b(or( else)?|otherwise|warna|varna|nahi to|failing which)\b"
    + _SAME_SENTENCE + r"{0,60}?" + _THREAT
    + r"|" + _THREAT + _SAME_SENTENCE + r"{0,80}?\bunless (you )?(pay|transfer|deposit|send)\b"
)
_NEGATED_PAYMENT = re.compile(r"\b(never|do not|don'?t|mat|nahi)\s+(\w+\s+)?(pay|transfer|send|bhej)")


def _is_payment_under_threat(text: str) -> bool:
    """"Pay 4999 now or a police case will be filed." A warning that names
    both ("never pay anyone who threatens arrest") is not one."""
    return bool(_PAYMENT_UNDER_THREAT.search(text)) and not _NEGATED_PAYMENT.search(text)


class TrustPassport:
    """Accumulates evidence across a call. Checks latch once resolved — a
    caller who asked for an OTP at 0:40 does not become trustworthy again by
    not asking for one at 1:20."""

    def __init__(self) -> None:
        self.claimed_identity: str | None = None
        self._checks: dict[str, CheckOut] = {}
        self._init_checks()

    def _init_checks(self) -> None:
        for name in (
            "Claimed identity",
            "Credential request",
            "Secrecy demand",
            "Payment to individual",
            "Call-back tolerance",
            "Procedural plausibility",
        ):
            self._checks[name] = CheckOut(name, "UNKNOWN", "not yet observed")

    def _cite(self, query: str) -> str | None:
        hits = get_kb().search(query, k=1)
        return hits[0].chunk.source if hits else None

    def observe(self, text: str, speaker: str = "CALLER") -> None:
        if speaker != "CALLER":
            return
        low = text.lower()

        if self.claimed_identity is None:
            for pattern, name in IDENTITY_PATTERNS:
                if re.search(pattern, low):
                    self.claimed_identity = name
                    self._checks["Claimed identity"] = CheckOut(
                        "Claimed identity",
                        "UNKNOWN",
                        f"claims {name} — unverifiable from the call itself",
                        self._cite("case numbers read out over the phone as proof"),
                    )
                    break

        # A credential request is dispositive on its own — but only if it is
        # actually a request. Genuine bank calls say "we never ask for your
        # OTP" and legitimate advisories say "never share your PIN", both of
        # which mention the credential in order to warn about it. Matching the
        # bare word flagged a real reminder call as CRITICAL, which is the
        # exact false positive that teaches users to ignore the system.
        if _is_credential_request(low):
            self._fail(
                "Credential request",
                "asked for a credential no institution ever requests",
                "banks and RBI never ask for OTP PIN CVV or passwords",
            )

        if _SECRECY.search(low) and not _SECRECY_ADVISORY.search(low):
            self._fail(
                "Secrecy demand",
                "required secrecy from family or threatened consequences for hanging up",
                "digital arrest is not a legal procedure secrecy from family",
            )

        if _SCAM_PAYMENT.search(low):
            self._fail(
                "Payment to individual",
                "asked for funds to be sent to prove innocence or secure a refund",
                "money is never seized by asking the owner to send it",
            )

        # Call-back intolerance. Only FAILs on an explicit refusal — the
        # absence of an offer to call back is not evidence of anything.
        if re.search(r"\b(call ?back (mat|nahi)|line mat kato|phone mat rakh|disconnect mat)\w*", low):
            self._fail(
                "Call-back tolerance",
                "refused to let the call be verified by calling back",
                "a genuine caller loses nothing if you verify them",
            )

        if re.search(r"\b(digital arrest|video call on rakh|warrant.*(2|two) (ghante|hours))\w*", low):
            self._fail(
                "Procedural plausibility",
                "described a procedure that does not exist in Indian law",
                "no agency conducts a digital arrest",
            )

        if _is_payment_under_threat(low):
            self._fail(
                "Procedural plausibility",
                "demanded payment to avoid arrest or a police case — no agency "
                "settles a criminal matter by a payment over the phone",
                "money is never seized by asking the owner to send it",
            )

    def _fail(self, name: str, detail: str, cite_query: str) -> None:
        existing = self._checks.get(name)
        if existing is not None and existing.verdict == "FAIL":
            return  # latched
        self._checks[name] = CheckOut(name, "FAIL", detail, self._cite(cite_query))

    def pass_check(self, name: str, detail: str) -> None:
        """Used by the benign path — e.g. a caller who volunteers a call-back
        number, or explicitly says they will never ask for an OTP."""
        existing = self._checks.get(name)
        if existing is not None and existing.verdict == "FAIL":
            return  # a FAIL is never un-failed
        self._checks[name] = CheckOut(name, "PASS", detail, None)

    def snapshot(self) -> PassportOut:
        checks = list(self._checks.values())
        resolved = [c for c in checks if c.verdict != "UNKNOWN"]
        if not resolved:
            # Nothing has been established either way. 50% is the honest
            # answer: not "trusted", not "fraudulent", just unevaluated.
            pct = 50.0
        else:
            passed = sum(1 for c in resolved if c.verdict == "PASS")
            pct = 100.0 * passed / len(resolved)
        # FAILs sort first — the reason a passport reads 0% should be the
        # first row, not buried under checks that never ran.
        order = {"FAIL": 0, "PASS": 1, "UNKNOWN": 2}
        checks.sort(key=lambda c: order[c.verdict])
        return PassportOut(
            claimed_identity=self.claimed_identity,
            final_trust_pct=round(pct, 1),
            checks=checks,
        )
