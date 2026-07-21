"""
Personalized AI guidance (CFSRP / Module 3, Step 3).

The PDF's design: guidance that *changes with the scam stage and threat level*,
not a static leaflet. Given the stage Module 1 detected and the current threat
band, this returns the specific protective actions for that moment — "do not
transfer money, end the call, do not share OTPs" during a payment request; a
calmer verification prompt during an authority claim.

The critical safety rule is the same one the coach follows: the *lines* a
frightened person is told come from the curated coach library, verbatim. This
module chooses which stage's guidance applies and assembles the action list; it
never writes a new instruction for someone mid-scam. An LLM is never in this path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..rag.coach import get_coach

# Stage → the ordered protective actions for that moment. Lifted from RBI / I4C
# advisories and the module 3 PDF's own worked example; kept short because a
# panicking person cannot act on ten bullet points.
_STAGE_ACTIONS: Dict[str, List[str]] = {
    "GREETING": [
        "You do not have to stay on this call. A real agency will send a written notice.",
        "Do not share any personal detail until you have independently verified who this is.",
    ],
    "AUTHORITY_CLAIM": [
        "No police, CBI, or court conducts investigations over a phone or video call.",
        "Hang up and call the agency back on a number you looked up yourself — never one they gave you.",
        "Ask for the claim in writing. A genuine officer can provide it; a scammer cannot.",
    ],
    "FEAR_INDUCTION": [
        "Slow down — fear is the tool. There is no legal case that a payment can make disappear.",
        "You cannot be arrested over a phone call. 'Digital arrest' is not a real thing.",
        "Tell one family member right now what is being said to you.",
    ],
    "ISOLATION": [
        "Being told to keep this secret is the clearest sign it is a scam. Break the isolation now.",
        "Do not stay on a video call under any circumstances. Disconnect.",
        "Call a trusted family member or friend immediately — do not stay alone with the caller.",
    ],
    "VERIFICATION_DEMAND": [
        "Never share an OTP, PIN, CVV, Aadhaar, or account number. No genuine agency asks for these.",
        "An OTP is a password. Reading it out loud hands over your account.",
        "Stop the call and check directly with your bank on the number printed on your card.",
    ],
    "PAYMENT_SETUP": [
        "Do not transfer money to any 'verification', 'refund', or 'supervised' account. These do not exist.",
        "No court, bank, or agency needs you to move money to prove your innocence.",
        "Call 1930 now and tell them a scam payment is being set up.",
    ],
    "PAYMENT_EXECUTION": [
        "STOP. Do not enter your UPI PIN or approve any transaction.",
        "Disconnect the call immediately and call 1930.",
        "If money has already gone, call your bank's fraud line now — the first hour is when it can be frozen.",
    ],
    "BENIGN": [
        "Nothing here matches the coercion patterns this system detects.",
        "Still verify any payment request in your own banking app before acting.",
    ],
}


@dataclass
class Guidance:
    stage: str
    threat_level: str
    headline: str
    actions: List[str]
    coach_line: Optional[str] = None
    coach_why: Optional[str] = None
    sources: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "threat_level": self.threat_level,
            "headline": self.headline,
            "actions": self.actions,
            "coach_line": self.coach_line,
            "coach_why": self.coach_why,
            "sources": self.sources,
        }


_HEADLINES = {
    "CRITICAL": "This is a scam in progress. Act now.",
    "HIGH": "This has the hallmarks of a scam. Do not comply.",
    "ELEVATED": "Treat this as suspicious until you have verified it independently.",
    "WATCH": "Some signals are concerning. Stay cautious.",
    "CALM": "No active coercion detected — but stay alert.",
}


def build_guidance(stage: str, threat_level: str) -> Guidance:
    """Assemble stage- and threat-appropriate guidance. The coach line is pulled
    verbatim from the curated library; the actions are the stage's checklist."""
    actions = list(_STAGE_ACTIONS.get(stage, _STAGE_ACTIONS["BENIGN"]))
    coach = get_coach().suggest(stage)
    return Guidance(
        stage=stage,
        threat_level=threat_level,
        headline=_HEADLINES.get(threat_level, _HEADLINES["WATCH"]),
        actions=actions,
        coach_line=coach.line if coach else None,
        coach_why=coach.why if coach else None,
        sources=coach.sources if coach else [],
    )
