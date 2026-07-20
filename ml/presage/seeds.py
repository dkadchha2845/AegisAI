"""
PRESAGE — diversity grid for synthetic call generation.

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
]

# --- Axis 3: scammer style --------------------------------------------------

SCAMMER_STYLES: list[dict[str, str]] = [
    {"id": "aggressive", "desc": "Loud, interrupting, threatening arrest within minutes."},
    {"id": "bureaucratic", "desc": "Flat, procedural, quotes fake section numbers and case IDs."},
    {"id": "friendly_helper", "desc": "Warm and sympathetic, positions himself as the victim's only ally."},
    {"id": "rushed_official", "desc": "Clipped and impatient, as if handling many cases at once."},
    {"id": "escalating_handoff", "desc": "Starts calm, then 'transfers' the call to a harsher senior officer."},
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
    n_scam: int = 220,
    n_benign: int = 110,
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
