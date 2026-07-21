"""
Emergency response engine (CFSRP / Module 3, Step 4).

When the threat is high, guidance is not enough — the citizen needs one-tap
access to the right helpline and a concrete checklist. This module holds the
official reporting directory (national and the numbers the PDF names) and builds
a severity-scaled action checklist.

Everything here is a static, verifiable directory: 1930 is the national
cyber-fraud helpline, cybercrime.gov.in is the I4C portal. No number is invented,
and the "one-tap" links are `tel:` / `https:` the frontend renders — the module
returns data, the app decides how to surface it. The PDF notes bank/telecom API
integration can be added later without changing this shape; the directory is
structured so a real bank fraud-line lookup slots in as another entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

# Official channels. These are public, national, and stable.
HELPLINES: List[Dict[str, str]] = [
    {
        "name": "National Cyber-Fraud Helpline",
        "value": "1930",
        "action": "tel:1930",
        "detail": "Report a financial cyber-fraud. Call within the first hour to give the "
                  "bank the best chance of freezing the transfer.",
        "priority": "primary",
    },
    {
        "name": "National Cybercrime Reporting Portal (I4C)",
        "value": "cybercrime.gov.in",
        "action": "https://cybercrime.gov.in",
        "detail": "File a formal complaint and upload evidence. Generates an acknowledgement number.",
        "priority": "primary",
    },
    {
        "name": "Police Emergency",
        "value": "112",
        "action": "tel:112",
        "detail": "For an immediate threat to safety.",
        "priority": "secondary",
    },
    {
        "name": "Report Spam / Fraud SMS & Calls (TRAI DND)",
        "value": "1909",
        "action": "tel:1909",
        "detail": "Report the number that contacted you to the telecom regulator.",
        "priority": "secondary",
    },
]


@dataclass
class EmergencyResponse:
    severity: str                    # info | warn | urgent
    title: str
    checklist: List[str]
    helplines: List[Dict[str, str]]
    show_panic_banner: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "title": self.title,
            "checklist": self.checklist,
            "helplines": self.helplines,
            "show_panic_banner": self.show_panic_banner,
        }


def build_response(threat_level: str, stage: str, *, payment_risk: bool) -> EmergencyResponse:
    """Severity-scaled emergency response. CRITICAL/HIGH with a payment stage
    shows the panic banner and the full freeze-the-money checklist; lower bands
    return calmer guidance."""
    critical = threat_level in ("CRITICAL", "HIGH")
    money_stage = stage in ("PAYMENT_SETUP", "PAYMENT_EXECUTION") or payment_risk

    if critical and money_stage:
        checklist = [
            "Do not transfer any money or approve any UPI request.",
            "Disconnect the call now — there is no legal penalty for hanging up.",
            "Call 1930 immediately and say a scam payment is being attempted.",
            "Call your bank's fraud line and ask them to freeze outgoing transfers.",
            "Do not delete any messages, call logs, or screenshots — they are evidence.",
            "Tell a family member what happened.",
        ]
        return EmergencyResponse("urgent", "Active scam — protect your money now",
                                 checklist, HELPLINES, True)

    if critical:
        checklist = [
            "Do not share any OTP, PIN, Aadhaar, or account detail.",
            "Hang up and independently verify the caller through an official number.",
            "Preserve all messages and screenshots as evidence.",
            "If anything has already been shared or paid, call 1930.",
        ]
        return EmergencyResponse("urgent", "High-risk contact — do not comply",
                                 checklist, HELPLINES, True)

    if threat_level == "ELEVATED":
        checklist = [
            "Treat this as suspicious. Do not act on anything in the message yet.",
            "Verify independently before sharing any information or making a payment.",
            "Keep the evidence in case you need to report it.",
        ]
        return EmergencyResponse("warn", "Suspicious — verify before you act",
                                 checklist, HELPLINES[:2], False)

    checklist = [
        "No active coercion detected, but stay cautious.",
        "Never share an OTP, PIN, or CVV — no genuine institution asks for them.",
        "Verify any payment request in your own banking app.",
    ]
    return EmergencyResponse("info", "Low risk — stay alert", checklist, HELPLINES[:2], False)
