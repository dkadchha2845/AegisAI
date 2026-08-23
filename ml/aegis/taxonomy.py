"""
AegisAI — scam-stage taxonomy.

The single source of truth for what the classifier predicts. Everything
downstream (the Markov twin's transition matrix, the manipulation map, the
coach library index, the threat fusion weights) keys off these labels, so
this file is imported rather than duplicated.

Design notes
------------
Eight labels, not more. Every extra class costs recall on the two that
actually matter -- ISOLATION and PAYMENT_EXECUTION -- because synthetic data
spreads thin. Stages are *speech acts*, not topics: a single utterance gets
exactly one label, chosen by what the speaker is trying to make happen.

BENIGN is the hard-negative class and is deliberately broad. It carries all
the legitimate calls that share surface vocabulary with scams ("verify",
"account", "urgent", "KYC"). Without it the model fires on every real bank
call, and a false-positive rate that annoys real users is the fastest way to
lose a judge's confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    """One scam stage: label, what it is, and how it actually sounds."""

    label: str
    order: int  # canonical position in the scam arc; BENIGN is -1
    summary: str
    intent: str  # what the speaker is trying to achieve
    markers: list[str] = field(default_factory=list)  # real Hinglish phrasings
    threat_weight: float = 0.0  # 0-1 contribution to the fusion threat score


STAGES: list[Stage] = [
    Stage(
        label="GREETING",
        order=0,
        summary="Opening contact, establishing the call frame.",
        intent="Get the victim to stay on the line and accept the premise.",
        markers=[
            "Hello, kya main Rajesh Kumar ji se baat kar raha hoon?",
            "Good morning sir, main customer care se bol raha hoon.",
            "Aapka ek minute time chahiye tha, important matter hai.",
            "Sir aap abhi free hain? Ek zaroori baat karni thi.",
        ],
        threat_weight=0.05,
    ),
    Stage(
        label="AUTHORITY_CLAIM",
        order=1,
        summary="Claiming institutional authority the caller does not have.",
        intent="Borrow the credibility of a feared or trusted institution.",
        markers=[
            "Main CBI Mumbai crime branch se Inspector Sharma bol raha hoon.",
            "Ye call TRAI ke regulation department se hai.",
            "Main aapke bank ke fraud prevention cell se bol raha hoon.",
            "Narcotics department, Andheri office. Mera badge number 4471 hai.",
            "Sir main Delhi Cyber Crime se ACP Verma speaking.",
        ],
        threat_weight=0.45,
    ),
    Stage(
        label="FEAR_INDUCTION",
        order=2,
        summary="Manufacturing a crisis with severe personal consequences.",
        intent="Replace the victim's deliberate thinking with panic.",
        markers=[
            "Aapke Aadhaar par ek parcel mila hai jisme drugs hain.",
            "Aapke naam par money laundering ka case register ho chuka hai.",
            "Arrest warrant issue ho chuka hai, 2 ghante mein police aayegi.",
            "Aapka number 24 ghante mein permanently block ho jayega.",
            "Ye ek non-bailable offence hai sir, samajh rahe hain aap?",
        ],
        threat_weight=0.7,
    ),
    Stage(
        label="ISOLATION",
        order=3,
        summary="Cutting the victim off from anyone who could interrupt.",
        intent="Remove every external reality-check before asking for money.",
        markers=[
            "Ye matter confidential hai, kisi ko batana mana hai.",
            "Call disconnect mat kariye, warna case aur serious ho jayega.",
            "Aap abhi akele hain? Kisi aur ko room mein mat aane dijiye.",
            "Family ko batayenge to unko bhi investigation mein involve karna padega.",
            "Digital arrest par hain aap, video call on rakhiye, kahin mat jaiye.",
        ],
        threat_weight=0.9,
    ),
    Stage(
        label="VERIFICATION_DEMAND",
        order=4,
        summary="Extracting identity or account credentials under pretext.",
        intent="Harvest the data needed to move money or impersonate.",
        markers=[
            "Apna Aadhaar number bataiye verification ke liye.",
            "Account mein kitna balance hai? Verify karna padega.",
            "Ek OTP aaya hoga, wo number bataiye.",
            "Aapke bank details confirm karni hain, last 4 digit bataiye.",
            "PAN card number aur date of birth chahiye hoga.",
        ],
        threat_weight=0.8,
    ),
    Stage(
        label="PAYMENT_SETUP",
        order=5,
        summary="Framing the transfer as safe, refundable, or official.",
        intent="Make handing over money feel like the responsible choice.",
        markers=[
            "Ye ek refundable security deposit hai, verification ke baad wapas mil jayega.",
            "RBI ke supervised account mein paisa transfer karna hoga.",
            "Aapke funds ko verify karne ke liye ek escrow account mein bhejna padega.",
            "Court fees ke liye abhi payment karni hogi, warna bail nahi milegi.",
            "Main aapko account number bhej raha hoon, note kar lijiye.",
        ],
        threat_weight=0.9,
    ),
    Stage(
        label="PAYMENT_EXECUTION",
        order=6,
        summary="Walking the victim through the transfer, step by step.",
        intent="Get the money to actually move, right now.",
        markers=[
            "UPI app kholiye, main batata hoon kya karna hai.",
            "Amount daaliye 4,50,000 aur confirm kar dijiye.",
            "Transaction ho gaya? Screenshot bhejiye abhi.",
            "IMPS se kariye, NEFT mein time lagega.",
            "PIN daal dijiye sir, main line par hoon.",
        ],
        threat_weight=1.0,
    ),
    Stage(
        label="BENIGN",
        order=-1,
        summary="Legitimate call, or ordinary conversation. The hard negative.",
        intent="Genuine business -- no manipulation, no coercion.",
        markers=[
            "Sir aapki credit card payment due hai, reminder call hai ye.",
            "Aapka order kal deliver hoga, address confirm kar lijiye.",
            "Hum kabhi OTP nahi maangte, dhyan rakhiyega.",
            "Aap branch mein aakar KYC complete kar sakte hain, koi jaldi nahi.",
            "Policy renewal ke liye call kiya tha, aap apne time par soch lijiye.",
        ],
        threat_weight=0.0,
    ),
]

LABELS: list[str] = [s.label for s in STAGES]
SCAM_LABELS: list[str] = [s.label for s in STAGES if s.label != "BENIGN"]
BY_LABEL: dict[str, Stage] = {s.label: s for s in STAGES}
THREAT_WEIGHTS: dict[str, float] = {s.label: s.threat_weight for s in STAGES}

# The two classes the demo lives or dies on. Report their recall separately in
# the deck -- macro-F1 alone hides a model that never catches the payment.
CRITICAL_LABELS: list[str] = ["ISOLATION", "PAYMENT_EXECUTION"]


def prompt_block() -> str:
    """Render the taxonomy as a prompt fragment for the generator."""
    lines = []
    for stage in sorted(STAGES, key=lambda s: (s.order < 0, s.order)):
        lines.append(f"- {stage.label}: {stage.summary} ({stage.intent})")
        for marker in stage.markers[:3]:
            lines.append(f"    e.g. {marker!r}")
    return "\n".join(lines)
