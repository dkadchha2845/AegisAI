"""
AegisAI — diversity grid for synthetic call generation.

The failure mode of LLM-generated datasets is mode collapse: ask for 200 scam
calls and you get 200 paraphrases of the same call. The classifier then scores
0.96 macro-F1 on a held-out split that is really the same distribution, and
falls over on the first real utterance that phrases things differently.

The fix is to never ask for "a scam call". Every generation request is
conditioned on a distinct point in a combinatorial grid -- archetype x victim
x scammer style x language mix x outcome -- so the model is forced to move
through the space instead of settling into its own prior.

Sampling is deterministic given a seed so a run is reproducible, and calls are
drawn without replacement across the archetype axis first (the axis that most
changes surface vocabulary) to guarantee even coverage rather than trusting
random sampling to be uniform at n=200.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import asdict, dataclass

# --- Axis 1: scam archetype -------------------------------------------------
# The dominant axis. Each archetype has its own vocabulary, its own pretext,
# and its own natural stage ordering, so this is what buys real diversity.

SCAM_ARCHETYPES: list[dict[str, str]] = [
    {
        "id": "digital_arrest",
        "name": "Digital arrest / CBI impersonation",
        "premise": "Caller poses as CBI/police claiming a parcel or bank account "
        "linked to the victim's Aadhaar is part of a money-laundering case, and "
        "places them under 'digital arrest' on a video call.",
    },
    {
        "id": "courier_parcel",
        "name": "FedEx / courier parcel scam",
        "premise": "Caller poses as a courier company saying a parcel in the "
        "victim's name was seized with contraband, then transfers the call to a "
        "fake police officer.",
    },
    {
        "id": "kyc_expiry",
        "name": "Bank KYC expiry",
        "premise": "Caller claims the victim's bank KYC has expired and the "
        "account will be frozen within hours unless verified immediately.",
    },
    {
        "id": "electricity_bill",
        "name": "Electricity disconnection",
        "premise": "Caller claims an unpaid electricity bill and threatens "
        "disconnection tonight unless a small payment is made via a link.",
    },
    {
        "id": "army_officer_olx",
        "name": "Armed-forces buyer marketplace scam",
        "premise": "Caller poses as an army officer buying the victim's listed "
        "item, insists on a 'test transfer' and sends a request-money QR code.",
    },
    {
        "id": "investment_returns",
        "name": "Investment / trading group",
        "premise": "Caller offers guaranteed returns through a private trading "
        "group, shows fake profits, then demands a deposit to withdraw.",
    },
    {
        "id": "loan_app_harassment",
        "name": "Instant loan app recovery",
        "premise": "Caller from a predatory loan app threatens to send edited "
        "photos to the victim's contacts unless an inflated amount is paid.",
    },
    {
        "id": "refund_overpayment",
        "name": "Refund overpayment",
        "premise": "Caller claims a refund was mistakenly overpaid and asks the "
        "victim to return the excess, walking them through screen sharing.",
    },
    {
        "id": "sim_swap_trai",
        "name": "TRAI / SIM disconnection",
        "premise": "Automated-sounding caller claims the victim's number is "
        "linked to illegal activity and will be disconnected in two hours.",
    },
    {
        "id": "job_offer_fee",
        "name": "Work-from-home job fee",
        "premise": "Caller offers a work-from-home job requiring a small "
        "registration and 'training kit' fee that keeps escalating.",
    },
    # --- New archetypes (15 more, for 25 total) ---
    {
        "id": "aadhaar_biometric",
        "name": "Aadhaar biometric update",
        "premise": "Caller claims the victim's Aadhaar biometric data has expired "
        "and they must pay a fee to update it remotely or face government "
        "penalties and service denial.",
    },
    {
        "id": "customs_duty",
        "name": "Customs duty payment",
        "premise": "Caller poses as customs officer saying a gift parcel from "
        "abroad is held at the port and the victim must pay duty and clearance "
        "charges via UPI to release it today.",
    },
    {
        "id": "credit_limit_upgrade",
        "name": "Credit card limit increase",
        "premise": "Caller claims the victim has been pre-approved for a credit "
        "limit increase and needs to verify identity and pay a processing fee "
        "to activate it before the offer expires.",
    },
    {
        "id": "epfo_pf_withdrawal",
        "name": "EPFO / PF withdrawal",
        "premise": "Caller poses as EPFO helpdesk saying the victim's PF "
        "withdrawal is stuck due to a KYC mismatch and demands Aadhaar, "
        "bank details, and a verification deposit to release the funds.",
    },
    {
        "id": "lottery_prize",
        "name": "Lottery / prize money",
        "premise": "Caller claims the victim has won a lottery or KBC prize and "
        "must pay tax and processing fees upfront before the prize can be "
        "released to their account.",
    },
    {
        "id": "irctc_ewallet",
        "name": "IRCTC / rail e-wallet scam",
        "premise": "Caller poses as IRCTC support claiming the victim's e-wallet "
        "has been flagged for suspicious activity and funds will be forfeited "
        "unless verified by transferring the balance to a safe account.",
    },
    {
        "id": "insurance_claim",
        "name": "Insurance claim clearance",
        "premise": "Caller claims a life insurance maturity payout is ready but "
        "requires an advance GST deposit and policy verification fee before "
        "the cheque can be dispatched.",
    },
    {
        "id": "income_tax_refund",
        "name": "Income tax refund",
        "premise": "Caller poses as Income Tax department saying the victim has a "
        "pending refund but their bank details don't match, and asks for PAN, "
        "Aadhaar, bank account, and a small verification transfer.",
    },
    {
        "id": "bank_account_closure",
        "name": "Bank account sudden closure",
        "premise": "Caller claims the victim's bank account has been flagged by "
        "RBI for suspicious transactions and will be permanently closed in "
        "one hour unless they verify identity and transfer funds to a holding account.",
    },
    {
        "id": "fake_rbi_circular",
        "name": "Fake RBI circular",
        "premise": "Caller poses as RBI official citing a new circular that "
        "requires all citizens to link their Aadhaar with all bank accounts "
        "immediately or face account freezing and a penalty.",
    },
    {
        "id": "hospital_emergency",
        "name": "Hospital emergency scam",
        "premise": "Caller claims to be from a hospital saying a relative has "
        "been admitted after an accident and requires an immediate deposit "
        "for emergency surgery, demanding secrecy and urgency.",
    },
    {
        "id": "wedding_card_malware",
        "name": "Wedding card APK scam",
        "premise": "Caller pretends to be a friend or relative and asks the "
        "victim to install a wedding invitation app (actually malware), then "
        "uses screen access to initiate transfers.",
    },
    {
        "id": "tech_support_remote",
        "name": "Tech support remote access",
        "premise": "Caller claims to be from Microsoft or a telecom company, "
        "says the victim's device is hacked, and insists on installing remote "
        "access software to 'fix' it while secretly initiating bank transfers.",
    },
    {
        "id": "fake_fir_settlement",
        "name": "Fake FIR settlement",
        "premise": "Caller claims an FIR has been filed against the victim for "
        "a traffic accident or cheque bounce and offers to settle it out of "
        "court for an immediate cash transfer.",
    },
    {
        "id": "crypto_investment",
        "name": "Crypto investment platform",
        "premise": "Caller promotes a crypto trading platform with guaranteed "
        "returns, shows fake dashboards, and demands increasing deposits to "
        "unlock withdrawals.",
    },
]

# --- The hard negatives -----------------------------------------------------
# These share vocabulary with the scams above ("verify", "account", "urgent",
# "KYC", "payment due") but are entirely legitimate. This class is what stops
# the model from flagging every real bank call. Roughly a third of the corpus
# should be drawn from here.

BENIGN_ARCHETYPES: list[dict[str, str]] = [
    {
        "id": "genuine_bank_alert",
        "name": "Genuine bank fraud alert",
        "premise": "A real bank officer calls about a suspicious transaction, "
        "explicitly refuses to ask for OTP or PIN, and directs the victim to the "
        "official app or branch.",
    },
    {
        "id": "genuine_delivery",
        "name": "Real delivery coordination",
        "premise": "A delivery agent calls to confirm the address and a "
        "convenient time. Mildly urgent, entirely ordinary.",
    },
    {
        "id": "genuine_police",
        "name": "Real police verification",
        "premise": "A local constable calls about tenant-verification paperwork "
        "and asks the resident to visit the station at their convenience. No "
        "money, no threat, no secrecy.",
    },
    {
        "id": "genuine_insurance",
        "name": "Insurance renewal reminder",
        "premise": "An agent reminds the customer about a policy renewal, "
        "answers questions, and accepts 'I'll think about it' without pressure.",
    },
    {
        "id": "genuine_kyc_branch",
        "name": "Legitimate KYC request",
        "premise": "A bank asks the customer to complete KYC at a branch within "
        "the next month. Sounds superficially like the KYC scam but has no "
        "deadline pressure, no link, and no request for credentials.",
    },
    {
        "id": "genuine_customer_support",
        "name": "Inbound customer support",
        "premise": "The customer called the company. Routine troubleshooting of "
        "a failed transaction, with the agent verifying identity through the "
        "official IVR flow only.",
    },
    {
        "id": "family_conversation",
        "name": "Ordinary family call",
        "premise": "A family member calls about everyday matters, possibly "
        "including money between relatives -- warm, informal, no coercion.",
    },
    # --- New benign archetypes (10 more, for 17 total) ---
    {
        "id": "hospital_appointment",
        "name": "Hospital appointment reminder",
        "premise": "A hospital receptionist calls to confirm an upcoming "
        "appointment, offers to reschedule, mentions no fees or urgency.",
    },
    {
        "id": "school_fee_reminder",
        "name": "School fee reminder",
        "premise": "A school office calls about pending fees for the next term. "
        "Mentions the amount and deadline but does not pressure or threaten.",
    },
    {
        "id": "emi_collection",
        "name": "EMI collection call",
        "premise": "A bank recovery agent calls about a missed EMI, reads the "
        "outstanding amount, offers restructuring, and tells the customer to "
        "pay through the app or branch.",
    },
    {
        "id": "telecom_plan_upgrade",
        "name": "Telecom plan upgrade offer",
        "premise": "A telecom executive calls about a new plan with better data. "
        "Quotes prices, asks if the customer is interested, accepts 'no' gracefully.",
    },
    {
        "id": "credit_card_reward",
        "name": "Credit card reward redemption",
        "premise": "A bank calls about expiring reward points, explains how to "
        "redeem them via the app, explicitly says no payment is needed.",
    },
    {
        "id": "property_broker",
        "name": "Property broker follow-up",
        "premise": "A real-estate broker follows up on a property inquiry. "
        "Discusses prices, arranges a site visit, no financial transaction on call.",
    },
    {
        "id": "doctor_followup",
        "name": "Doctor follow-up call",
        "premise": "A clinic calls to check on a patient's recovery after a "
        "procedure, asks about medication side effects, schedules a review visit.",
    },
    {
        "id": "mutual_fund_sip",
        "name": "Mutual fund SIP reminder",
        "premise": "A financial advisor calls about an upcoming SIP debit, "
        "confirms the amount and date, and reminds the customer to maintain "
        "sufficient balance. No credentials asked.",
    },
    {
        "id": "gas_cylinder_booking",
        "name": "Gas cylinder booking",
        "premise": "An LPG distributor calls to confirm a cylinder delivery slot. "
        "Mentions the subsidised price and asks for a convenient delivery time.",
    },
    {
        "id": "electricity_meter_reading",
        "name": "Electricity meter reading",
        "premise": "A utility company calls because the meter reader could not "
        "access the premises, asks for a convenient day to visit, mentions no "
        "penalties or payments.",
    },
]

# --- Axis 2: victim persona -------------------------------------------------

VICTIM_PERSONAS: list[dict[str, str]] = [
    {
        "id": "retired_teacher",
        "desc": "68-year-old retired schoolteacher in Pune. Polite, deferential "
        "to authority, low tech literacy, becomes flustered quickly.",
    },
    {
        "id": "young_professional",
        "desc": "27-year-old IT professional in Bengaluru. Sceptical, asks "
        "pointed questions, but rushed and distracted during work hours.",
    },
    {
        "id": "small_shop_owner",
        "desc": "45-year-old shop owner in Surat. Streetwise about cash but "
        "unfamiliar with digital fraud. Worries about business reputation.",
    },
    {
        "id": "homemaker",
        "desc": "52-year-old homemaker in Lucknow. Defers financial decisions to "
        "her husband, which the scammer works around by demanding secrecy.",
    },
    {
        "id": "college_student",
        "desc": "20-year-old student in Delhi. Confident with apps but has "
        "little money and panics about anything involving police.",
    },
    {
        "id": "govt_employee",
        "desc": "50-year-old government clerk in Bhopal. Highly sensitive to "
        "anything threatening his service record or pension.",
    },
    # --- New personas (4 more, for 10 total) ---
    {
        "id": "nri_parent",
        "desc": "72-year-old retired bank manager in Jaipur whose children live "
        "abroad. Lonely, trusts official-sounding callers, slow with smartphones.",
    },
    {
        "id": "farmer",
        "desc": "55-year-old farmer in rural Maharashtra. Limited English, "
        "recently started using UPI for mandi payments, trusts anyone who "
        "sounds like they know technology.",
    },
    {
        "id": "startup_founder",
        "desc": "32-year-old startup founder in Hyderabad. Tech-savvy, "
        "impatient, multi-tasks during calls, quick to dismiss but also "
        "quick to comply if the right authority is invoked.",
    },
    {
        "id": "widow_pensioner",
        "desc": "65-year-old widow in Kolkata living on a government pension. "
        "Anxious about finances, no family nearby, extremely deferential "
        "to anyone claiming to be from the government.",
    },
]

# --- Axis 3: scammer style --------------------------------------------------

SCAMMER_STYLES: list[dict[str, str]] = [
    {"id": "aggressive", "desc": "Loud, interrupting, threatening arrest within minutes."},
    {"id": "bureaucratic", "desc": "Flat, procedural, quotes fake section numbers and case IDs."},
    {"id": "friendly_helper", "desc": "Warm and sympathetic, positions himself as the victim's only ally."},
    {"id": "rushed_official", "desc": "Clipped and impatient, as if handling many cases at once."},
    {"id": "escalating_handoff", "desc": "Starts calm, then 'transfers' the call to a harsher senior officer."},
    # --- New styles (3 more, for 8 total) ---
    {"id": "soft_spoken_female", "desc": "Soft-spoken woman, polite and patient, builds false trust before striking."},
    {"id": "tech_jargon", "desc": "Uses heavy technical jargon — IP addresses, server logs, encryption — to intimidate."},
    {"id": "emotional_guilt", "desc": "Guilt-trips the victim, says 'I am trying to help you but you are not cooperating'."},
]

# --- Axis 4: language mix ---------------------------------------------------
# Sarvam/Whisper output is romanised code-mixed text, so the training data must
# be too. Matching the ASR's actual output format matters more than linguistic
# tidiness.

LANGUAGE_MIXES: list[dict[str, str]] = [
    {"id": "hindi_heavy", "desc": "Mostly Hindi in Roman script, occasional English nouns (account, police, payment)."},
    {"id": "balanced", "desc": "Even Hinglish code-mixing, switching language mid-sentence."},
    {"id": "english_heavy", "desc": "Mostly Indian English with Hindi discourse markers (achha, theek hai, arre)."},
    {"id": "marathi_tinted", "desc": "Hinglish with occasional Marathi words (kaay, barobar, ho)."},
    {"id": "tamil_tinted", "desc": "Indian English with occasional Tamil words (seri, illa, enna)."},
]

# --- Axis 5: outcome --------------------------------------------------------
# Not every call ends in a transfer. A corpus of only successful scams teaches
# the twin that ISOLATION always leads to PAYMENT, which destroys the forecast's
# calibration and makes the demo's confidence number a lie.

OUTCOMES: list[dict[str, str]] = [
    {"id": "complied", "desc": "Victim complies and the transfer goes through."},
    {"id": "resisted", "desc": "Victim grows suspicious mid-call and starts pushing back."},
    {"id": "hung_up", "desc": "Victim disconnects abruptly partway through."},
    {"id": "interrupted", "desc": "A family member intervenes and the victim breaks off."},
    {"id": "stalled", "desc": "Victim stalls and asks to call back later; scammer escalates pressure."},
]

LENGTHS: list[dict[str, str]] = [
    {"id": "short", "desc": "8-14 turns. Fast, high-pressure."},
    {"id": "medium", "desc": "16-26 turns. The typical shape."},
    {"id": "long", "desc": "28-40 turns. Slow burn with repeated reassurance."},
]


@dataclass(frozen=True)
class Seed:
    """One point in the grid -- the full conditioning for a single call."""

    call_id: str
    is_scam: bool
    archetype_id: str
    archetype_name: str
    premise: str
    victim: str
    style: str
    language: str
    outcome: str
    length: str

    def as_dict(self) -> dict:
        return asdict(self)


def build_seeds(
    n_scam: int = 600,
    n_benign: int = 400,
    seed: int = 20260720,
) -> list[Seed]:
    """
    Build a reproducible, evenly-covered set of generation seeds.

    Archetypes are cycled rather than sampled so every one gets equal
    representation; the remaining axes are sampled independently. The default
    2:1 scam:benign ratio keeps BENIGN well-represented enough to actually
    suppress false positives without swamping the seven scam stages.
    """
    rng = random.Random(seed)
    seeds: list[Seed] = []

    def _draw(is_scam: bool, archetypes: list[dict[str, str]], count: int, tag: str):
        cycle = itertools.cycle(archetypes)
        for i in range(count):
            arch = next(cycle)
            seeds.append(
                Seed(
                    call_id=f"{tag}_{i:04d}_{arch['id']}",
                    is_scam=is_scam,
                    archetype_id=arch["id"],
                    archetype_name=arch["name"],
                    premise=arch["premise"],
                    victim=rng.choice(VICTIM_PERSONAS)["desc"],
                    style=rng.choice(SCAMMER_STYLES)["desc"],
                    language=rng.choice(LANGUAGE_MIXES)["desc"],
                    # A benign call has no scam "outcome" to speak of.
                    outcome=rng.choice(OUTCOMES)["desc"] if is_scam else "Call ends normally.",
                    length=rng.choice(LENGTHS)["desc"],
                )
            )

    _draw(True, SCAM_ARCHETYPES, n_scam, "scam")
    _draw(False, BENIGN_ARCHETYPES, n_benign, "benign")
    rng.shuffle(seeds)
    return seeds
