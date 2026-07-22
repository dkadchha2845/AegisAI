"""
Label space for the RSSIE multi-head model.

The spec (Section 13) asks each training sample to carry: Scam/Benign, Scam
Type, Conversation Stage, Emotional State, Behavioural State, Financial
Transfer Outcome, Number Spoofing Label, Video Metadata Label, Threat Level.

The committed corpus carries three of those directly — stage, victim_state, and
is_scam — plus the archetype each call was generated from. This module derives
the rest from what is actually labelled, and is explicit about which are
*supervised* and which are *derived*, because that distinction decides what any
reported metric means.

    SUPERVISED (real labels, learned)
        scam_binary       from seed.is_scam
        stage             from turn.stage — human/LLM-assigned, validated
        emotion           from turn.victim_state, widened to 8 states
        scam_type         from seed.archetype_id, a deterministic 1:1 mapping

    DERIVED (functions of other labels, NOT independent supervision)
        transfer_risk     from stage position on the arc
        threat_level      from the fusion engine at serving time

The derived ones are trained as auxiliary heads because they regularise the
shared encoder, not because a good score on them is evidence of anything. A
transfer-risk head that predicts a deterministic function of the stage label is
measuring the stage head twice. That is stated here so nobody quotes it as an
independent result later.

Number-spoofing and video-metadata labels are *not* derived. The corpus has no
telephony or video metadata at all — it is text transcripts — so inventing
those labels would be fabrication. Those two signals are produced entirely by
the rule-based extractors at serving time, which is honest and is why they
carry citations rather than confidence scores.
"""

from __future__ import annotations

#: Stage label space. Identical to ml/train.py's, and it must stay identical:
#: the two models share a serving interface and a corpus, and a reordering here
#: would silently mis-decode there.
STAGES = [
    "GREETING",
    "AUTHORITY_CLAIM",
    "FEAR_INDUCTION",
    "ISOLATION",
    "VERIFICATION_DEMAND",
    "PAYMENT_SETUP",
    "PAYMENT_EXECUTION",
    "BENIGN",
]

#: Scam-type label space. Mirrors `ScamType` in schema/models.py exactly; the
#: contract check does not cover this file, so it is asserted in
#: tests/test_kavach.py instead.
SCAM_TYPES = [
    "NONE",
    "DIGITAL_ARREST",
    "COURIER_PARCEL",
    "KYC_EXPIRY",
    "REFUND_OVERPAYMENT",
    "INVESTMENT_RETURNS",
    "LOAN_APP_HARASSMENT",
    "SIM_TRAI_DISCONNECTION",
    "UTILITY_DISCONNECTION",
    "JOB_OFFER_FEE",
    "LOTTERY_PRIZE",
    "TECH_SUPPORT_REMOTE",
    "UNKNOWN",
]

#: Eight-state emotion space. Mirrors `EmotionState` in schema/models.py.
EMOTIONS = [
    "CALM",
    "CURIOUS",
    "CONFUSED",
    "FEARFUL",
    "PANICKED",
    "TRUSTING",
    "RESISTANT",
    "COMPLIANT",
]

STAGE2ID = {s: i for i, s in enumerate(STAGES)}
SCAMTYPE2ID = {s: i for i, s in enumerate(SCAM_TYPES)}
EMOTION2ID = {s: i for i, s in enumerate(EMOTIONS)}

#: Archetype id (ml/presage/seeds.py) → scam type.
#:
#: Several distinct archetypes intentionally collapse onto one type. An EPFO
#: withdrawal scam, an income-tax refund scam and a fake-RBI-circular scam all
#: run the *same* playbook — impersonate a financial authority, allege an
#: account problem, demand verification then a transfer — and differ only in
#: the institution named. Giving each its own class would split an already thin
#: corpus into slices too small to learn, for a distinction that changes
#: nothing about the coaching or the reporting category.
_ARCHETYPE_TO_TYPE = {
    # Digital arrest / law-enforcement impersonation
    "digital_arrest": "DIGITAL_ARREST",
    "fake_fir_settlement": "DIGITAL_ARREST",
    "aadhaar_biometric": "DIGITAL_ARREST",
    # Courier / customs
    "courier_parcel": "COURIER_PARCEL",
    "customs_duty": "COURIER_PARCEL",
    # Bank/authority account-status pretexts
    "kyc_expiry": "KYC_EXPIRY",
    "bank_account_closure": "KYC_EXPIRY",
    "fake_rbi_circular": "KYC_EXPIRY",
    "credit_limit_upgrade": "KYC_EXPIRY",
    "epfo_pf_withdrawal": "KYC_EXPIRY",
    "income_tax_refund": "KYC_EXPIRY",
    "insurance_claim": "KYC_EXPIRY",
    "irctc_ewallet": "KYC_EXPIRY",
    # Refund / overpayment
    "refund_overpayment": "REFUND_OVERPAYMENT",
    "army_officer_olx": "REFUND_OVERPAYMENT",
    # Investment
    "investment_returns": "INVESTMENT_RETURNS",
    "crypto_investment": "INVESTMENT_RETURNS",
    # Loan harassment
    "loan_app_harassment": "LOAN_APP_HARASSMENT",
    # Telecom
    "sim_swap_trai": "SIM_TRAI_DISCONNECTION",
    # Utility
    "electricity_bill": "UTILITY_DISCONNECTION",
    # Employment
    "job_offer_fee": "JOB_OFFER_FEE",
    # Prize
    "lottery_prize": "LOTTERY_PRIZE",
    # Remote access / malware
    "tech_support_remote": "TECH_SUPPORT_REMOTE",
    "wedding_card_malware": "TECH_SUPPORT_REMOTE",
    "hospital_emergency": "DIGITAL_ARREST",
}


def scam_type_of_archetype(archetype_id: str, is_scam: bool) -> str:
    """Map a corpus archetype to its scam type.

    A benign call is NONE, never UNKNOWN. The distinction is the same one the
    contract draws: NONE means "checked, no scam"; UNKNOWN means "could not
    tell", and a legitimate call the generator produced deliberately is not an
    uncertain case.
    """
    if not is_scam:
        return "NONE"
    return _ARCHETYPE_TO_TYPE.get(archetype_id, "UNKNOWN")


#: Victim state (corpus) → emotion (8-state).
#:
#: This widening is lossy in the direction that matters and cannot be fixed by
#: mapping alone: the corpus never distinguishes CURIOUS from CALM, or TRUSTING
#: from CALM, because `VICTIM_STATES` in ml/presage/schema.py has no such
#: labels. So the trained emotion head can only ever predict six of the eight
#: classes, and the two it cannot predict are the two the rule-based extractor
#: in engine/features/emotion.py was written specifically to catch.
#:
#: That is why emotion is served from the rule-based tracker and the trained
#: head is auxiliary. Documented here rather than discovered later.
_VICTIM_TO_EMOTION = {
    "NA": None,          # caller turn — no victim emotion to label
    "CALM": "CALM",
    "CONFUSED": "CONFUSED",
    "ANXIOUS": "FEARFUL",
    "PANICKED": "PANICKED",
    "COMPLIANT": "COMPLIANT",
    "RESISTING": "RESISTANT",
}

#: The two emotion classes the corpus cannot supervise. Asserted in tests so
#: this stays true if the corpus schema changes.
UNSUPERVISED_EMOTIONS = ["CURIOUS", "TRUSTING"]


def emotion_of_victim_state(victim_state: str) -> str | None:
    """Widen a corpus victim state to the 8-state space. None for caller turns."""
    return _VICTIM_TO_EMOTION.get(victim_state)


#: Stage → financial transfer risk. A deterministic function of arc position,
#: which is exactly why it is auxiliary rather than a headline metric.
#:
#: The jump between VERIFICATION_DEMAND (0.55) and PAYMENT_SETUP (0.85) is the
#: intervention window this whole module exists to open. Credentials being
#: harvested is bad; an account number being dictated means the transfer is
#: minutes away.
_STAGE_RISK = {
    "GREETING": 0.05,
    "AUTHORITY_CLAIM": 0.20,
    "FEAR_INDUCTION": 0.40,
    "ISOLATION": 0.60,
    "VERIFICATION_DEMAND": 0.55,
    "PAYMENT_SETUP": 0.85,
    "PAYMENT_EXECUTION": 1.00,
    "BENIGN": 0.00,
}


def transfer_risk_of_stage(stage: str) -> float:
    return _STAGE_RISK.get(stage, 0.0)


def risk_band(risk: float) -> str:
    if risk >= 0.85:
        return "CRITICAL"
    if risk >= 0.6:
        return "HIGH"
    if risk >= 0.3:
        return "MEDIUM"
    return "LOW"
