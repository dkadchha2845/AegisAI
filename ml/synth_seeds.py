#!/usr/bin/env python3
"""
AegisAI — deterministic synthetic seed generator (Track 3, corpus expansion).

The STATUS P0: the fine-tuned MuRIL memorises call *archetypes* instead of
learning *stages*, because 16 archetypes with 8 held out for test is too few for
an 8-way classifier to be forced to generalise. The measured fix is more data,
and specifically more archetypes with denser coverage of the starved stages
(ISOLATION, VERIFICATION_DEMAND) and a wider spread of BENIGN.

This generates exactly that, offline and deterministically — no LLM key, no
network (Gemini's free quota is exhausted, and a corpus step must never depend on
a service that can 429). It composes new gold-format call skeletons from
stage-specific Hinglish phrase banks across many *new* archetypes, walking the
full manipulation arc and weighting the starved stages. The output is written to
`data/seed/exemplars_synth.jsonl` in the same schema as the hand-written gold, so
the existing `paraphrase.py --no-llm` expands it with entity substitution and
`build_dataset.py` splits it — the pipeline is unchanged, only the seed pool grows.

These are templated, and that is acknowledged: they add *breadth of archetype*,
which is the axis the leave-archetypes-out split rewards, on top of the natural
phrasing variety the existing LLM-and-substitution corpus already has. Whether
the enlarged corpus lets MuRIL beat the lexical baseline is then measured
honestly by `eval_backends.py` — promotion stays gated on that number, never on
this file existing.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "data" / "seed" / "exemplars_synth.jsonl"

# --- Phrase banks, per stage. Each entry is caller-side Hinglish; victim
#     reactions are drawn from a shared bank. Real names/cities/amounts are used
#     literally so entity substitution can vary them across the 20 variants.

GREETING = [
    "Hello, kya main {name} ji se baat kar raha hoon?",
    "Good afternoon sir, {name} ji ka number hai na ye?",
    "Namaste, main {org} se bol raha hoon, aapse ek zaroori baat karni thi.",
    "Sir aap {name} bol rahe hain? Ek minute time chahiye tha.",
    "Hello ji, {name}? Main {org} ke verification department se hoon.",
]

AUTHORITY = [
    "Main {org} se {rank} {surname} bol raha hoon, badge number {num}.",
    "Ye call {org} ke official department se hai, recorded line par hai.",
    "Sir main {org} {city} branch se speaking, mera ID {num} hai.",
    "Main {org} ka authorised officer hoon, aapka case mere paas aaya hai.",
    "{org} se bol raha hoon sir, ye ek official verification call hai.",
]

FEAR = [
    "Aapke naam par {city} mein ek case register hua hai, serious matter hai.",
    "Aapke Aadhaar par ek parcel mila hai jisme illegal items the.",
    "Aapke account se suspicious transaction hui hai, {amount} rupaye ki.",
    "Ye ek non-bailable offence hai sir, {hours} ghante mein action hoga.",
    "Aapka number {hours} ghante mein permanently block ho jayega agar verify nahi kiya.",
    "Court se warrant issue ho chuka hai, abhi cooperate karna zaroori hai.",
]

# Every phrase carries a varying entity ({surname}/{num}/{city}/{amount}/{org})
# so the 18 substitution variants stay distinct after the build's near-duplicate
# de-dup — otherwise the starved stages collapse to one utterance each. The
# entity is noise the classifier should ignore; keeping the stage-discriminative
# wording constant across varied entities is exactly what teaches "stage, not
# archetype".
ISOLATION = [
    "Case {num} confidential hai {surname} ji, kisi ko batana mana hai.",
    "Call disconnect mat kariye {surname} ji, warna case {num} aur serious ho jayega.",
    "Aap abhi akele hain {surname} ji? {city} team monitor kar rahi hai, kisi ko room mein mat aane dijiye.",
    "Family ko batayenge to unhe bhi FIR {num} mein involve karna padega.",
    "Aap digital arrest par hain, video call on rakhiye, {city} se officer connected hain.",
    "Kisi bank staff se baat mat kariye, wo case {num} leak kar sakte hain.",
    "Ye call recorded hai {surname} ji, seedha {org} ke instructions follow kariye.",
    "Aapko surveillance par rakha gaya hai, phone kaata to {city} arrest team bhej denge.",
    "Ye matter {org} internal hai, kisi third party ko involve mat kariye {surname} ji.",
    "Investigation {num} ke chalte aapko koi aur call attend nahi karni hai.",
]

VERIFICATION = [
    "Case {num} verify karne ke liye apna Aadhaar number bataiye {surname} ji.",
    "Aapke {org} account mein kitna balance hai? Confirm karna padega.",
    "Abhi ek OTP aaya hoga reference {num} ke saath, wo number bataiye jaldi.",
    "{org} ke record se milane ke liye card ke last 4 digit bataiye.",
    "PAN number aur date of birth chahiye verification {num} ke liye.",
    "Registered mobile par code aayega {surname} ji, wo mujhe padh kar sunaiye.",
    "Net banking user ID bata dijiye, sirf case {num} verify karna hai.",
    "KYC cross-check ke liye full naam aur DOB bataiye, ref {num}.",
    "Aapke {city} branch account ka IFSC aur account number confirm kariye.",
    "Security question ke liye mother ka naam bataiye, verification {num}.",
]

PAYMENT_SETUP = [
    "Ye refundable security deposit hai {surname} ji, case {num} clear hone par wapas.",
    "{org} ke supervised account mein {amount} transfer karna hoga safety ke liye.",
    "Funds verify karne ke liye escrow account {num} mein {amount} bhejna padega.",
    "Court fees {amount} abhi bharni hogi {surname} ji, warna bail nahi milegi.",
    "Main {org} ka account number bhej raha hoon, {amount} note kar lijiye.",
    "Clearance charge {amount} hai, refundable, {city} treasury account mein daaliye.",
    "Penalty {amount} deposit kariye reference {num} ke saath abhi.",
]

PAYMENT_EXECUTION = [
    "UPI app kholiye {surname} ji, {amount} ka transfer batata hoon step by step.",
    "Amount daaliye {amount} aur reference {num} ke saath confirm kar dijiye.",
    "Transaction {num} ho gaya? Screenshot bhejiye turant.",
    "IMPS se {amount} kariye, NEFT mein time lagega, jaldi kariye {surname} ji.",
    "PIN daal dijiye, main line par hi hoon, {amount} pending hai mat kaatiye.",
    "QR code scan kariye jo bheja hai, phir {amount} enter kariye.",
    "{upi} par {amount} send kar dijiye, ye {org} recovery account hai.",
    "GPay kholiye {surname} ji, {upi} add karke {amount} bhej dijiye abhi.",
]

# Benign — legitimate calls using overlapping vocabulary. Deliberately broad.
BENIGN_CALLS = [
    [
        ("GREETING", "Hello, main {org} customer care se {name} bol rahi hoon."),
        ("BENIGN", "Sir aapki credit card payment {amount} due hai, ye ek reminder call hai."),
        ("BENIGN", "Hum kabhi OTP ya PIN nahi maangte, dhyan rakhiyega."),
        ("BENIGN", "Aap net banking se ya branch mein jaakar pay kar sakte hain, koi jaldi nahi."),
    ],
    [
        ("GREETING", "Namaste, {org} se bol raha hoon, aapka order confirm karna tha."),
        ("BENIGN", "Aapka parcel kal deliver hoga, address confirm kar lijiye."),
        ("BENIGN", "Delivery ke time OTP bataiye, wo delivery boy verify karega."),
        ("BENIGN", "Koi payment abhi nahi karni, cash on delivery hai aapka order."),
    ],
    [
        ("GREETING", "Good morning, main aapke bank se relationship manager bol raha hoon."),
        ("BENIGN", "Aapki FD maturity aane wali hai, renew karna chahenge ya withdraw?"),
        ("BENIGN", "Aap apne time par branch aakar decide kar sakte hain, koi rush nahi."),
        ("BENIGN", "Main koi detail phone par nahi maangunga, bas information de raha hoon."),
    ],
    [
        ("GREETING", "Hello, {org} se policy renewal ke liye call kiya tha."),
        ("BENIGN", "Aapki insurance premium due hai, aap online ya branch se pay kar sakte hain."),
        ("BENIGN", "Koi jaldi nahi hai, grace period bhi milta hai aapko."),
        ("BENIGN", "Hum OTP ya card details kabhi phone par nahi lete."),
    ],
    [
        ("GREETING", "Namaste, ye {org} ka appointment reminder call hai."),
        ("BENIGN", "Aapka doctor appointment kal 5 baje hai, confirm karna tha."),
        ("BENIGN", "Reschedule karna ho to app se kar sakte hain."),
        ("BENIGN", "Koi payment ya detail ki zaroorat nahi, sirf reminder hai."),
    ],
    [
        ("GREETING", "Hello sir, main {org} se bol raha hoon aapke mobile ke baare mein."),
        ("BENIGN", "Aapka plan upgrade {amount} ka available hai, interested hon to bataiye."),
        ("BENIGN", "Aap {org} app se ya store jaakar change kar sakte hain."),
        ("BENIGN", "Hum kabhi OTP nahi maangte {name} ji, wo sirf aapke liye hota hai."),
    ],
    [
        ("GREETING", "Namaste {name} ji, {org} se statement ke baare mein call kiya tha."),
        ("BENIGN", "Aapka monthly statement ready hai, {amount} ka transaction dikha raha hai."),
        ("BENIGN", "Agar ye aapne kiya hai to koi action nahi chahiye, warna app se report kariye."),
        ("BENIGN", "Main kabhi PIN ya OTP nahi maangunga, sirf inform kar raha hoon."),
    ],
    [
        ("GREETING", "Hello {name} ji, {org} rewards program se bol raha hoon."),
        ("BENIGN", "Aapke {amount} reward points expire ho rahe hain, redeem kar sakte hain app se."),
        ("BENIGN", "Ye bilkul optional hai, koi payment ya detail nahi chahiye."),
        ("BENIGN", "Aap apne time par app kholkar dekh lijiye, koi jaldi nahi."),
    ],
]

VICTIM_REACTIONS = {
    "GREETING": ["Haan ji bol raha hoon, aap kaun?", "Ji boliye, kya baat hai?"],
    "AUTHORITY_CLAIM": ["Achha... kya hua sir?", "Kaunsa department bola aapne?"],
    "FEAR_INDUCTION": ["Nahi nahi, maine to kuch nahi kiya!", "Sir mera dil... ye kaise hua?"],
    "ISOLATION": ["Theek hai, main kisi ko nahi bataunga.", "Main akela hoon sir."],
    "VERIFICATION_DEMAND": ["Ek minute... par ye kyun chahiye?", "OTP to abhi aaya hai..."],
    "PAYMENT_SETUP": ["Itne paise? Par ye safe hai na?", "Account number bataiye phir."],
    "PAYMENT_EXECUTION": ["Ruk jaiye, main app khol raha hoon.", "Transfer kar diya sir..."],
    "BENIGN": ["Achha theek hai, dhanyavaad.", "Ok samajh gaya, thank you."],
}

# New archetypes not present in the hand-written gold — breadth is the point.
ARCHETYPES = [
    ("fake_court_summons", "Fake court summons", "Delhi High Court"),
    ("gst_fraud_notice", "GST fraud notice", "GST Department"),
    ("telegram_task_scam", "Telegram task / prepaid scam", "TaskEarn Team"),
    ("fake_lottery_kbc", "KBC lottery winner scam", "KBC Lucky Draw"),
    ("sextortion_video", "Video-call sextortion", "Cyber Cell"),
    ("fastag_recharge", "FASTag recharge fraud", "FASTag Support"),
    ("pension_verification", "Pension verification scam", "Pension Office"),
    ("scholarship_fee", "Scholarship processing fee", "Scholarship Board"),
    ("fake_job_interview", "Fake job interview fee", "HR Recruitment"),
    ("crypto_recovery", "Crypto recovery scam", "Asset Recovery Cell"),
    ("insurance_bonus", "Lapsed insurance bonus scam", "IRDAI Helpdesk"),
    ("sim_kyc_reverify", "SIM KYC re-verification", "Telecom Regulatory"),
    ("digital_house_arrest", "Digital house arrest (ED)", "Enforcement Directorate"),
    ("parcel_narcotics", "Parcel narcotics (Customs)", "Customs Department"),
    ("electricity_night_cut", "Electricity night disconnection", "Electricity Board"),
    ("bank_account_freeze", "Bank account freeze scam", "RBI Fraud Cell"),
]

RANKS = ["Inspector", "Sub-Inspector", "Officer", "ACP", "DCP", "Head Constable"]
SURNAMES = ["Sharma", "Verma", "Rana", "Malhotra", "Sinha", "Rao", "Khan", "Das"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Pune", "Jaipur"]
AMOUNTS = ["50,000", "1,20,000", "2,45,000", "75,000", "4,50,000", "18,500", "3,10,000"]
UPIS = ["recovery.node@okaxis", "verify.settle@oksbi", "clear.case@okhdfcbank"]


def _pick(rng, bank, **fmt):
    return rng.choice(bank).format(**fmt)


def make_scam_call(rng, idx, archetype):
    arch_id, arch_name, org = archetype
    name = rng.choice(["Ramesh", "Sunita", "Anil", "Priya", "Vikram", "Meera"]) + " " + rng.choice(SURNAMES)
    ctx = dict(
        name=name, org=org, rank=rng.choice(RANKS), surname=rng.choice(SURNAMES),
        num=str(rng.randint(1000, 9999)), city=rng.choice(CITIES),
        amount=rng.choice(AMOUNTS), hours=rng.choice(["2", "24", "48"]),
        upi=rng.choice(UPIS),
    )

    def caller(stage, bank, n=1):
        return [
            {"speaker": "CALLER", "text": _pick(rng, bank, **ctx), "stage": stage, "victim_state": "NA"}
            for _ in range(n)
        ]

    def victim(stage):
        return [{"speaker": "VICTIM", "text": rng.choice(VICTIM_REACTIONS[stage]),
                 "stage": stage, "victim_state": "ANXIOUS"}]

    turns = []
    turns += caller("GREETING", GREETING) + victim("GREETING")
    turns += caller("AUTHORITY_CLAIM", AUTHORITY) + victim("AUTHORITY_CLAIM")
    turns += caller("FEAR_INDUCTION", FEAR, n=2) + victim("FEAR_INDUCTION")
    # Starved stages get extra caller turns — this is the whole point.
    turns += caller("ISOLATION", ISOLATION, n=2) + victim("ISOLATION")
    turns += caller("VERIFICATION_DEMAND", VERIFICATION, n=2) + victim("VERIFICATION_DEMAND")
    turns += caller("PAYMENT_SETUP", PAYMENT_SETUP) + victim("PAYMENT_SETUP")
    turns += caller("PAYMENT_EXECUTION", PAYMENT_EXECUTION, n=2) + victim("PAYMENT_EXECUTION")

    return {
        "seed": {
            "call_id": f"synth_{idx:04d}_{arch_id}",
            "is_scam": True,
            "archetype_id": arch_id,
            "archetype_name": arch_name,
            "premise": f"Synthetic {arch_name} call walking the full manipulation arc.",
            "victim": "Adult in an Indian metro, variable tech literacy.",
            "style": "Composed from stage phrase banks.",
            "language": "Romanised Hinglish.",
            "outcome": rng.choice(["complies", "hangs up", "hesitates"]),
            "length": "medium",
        },
        "source": "synthetic_stage_bank",
        "turns": turns,
    }


def make_benign_call(rng, idx, template):
    name = rng.choice(["Ramesh", "Sunita", "Anil", "Priya"]) + " " + rng.choice(SURNAMES)
    org = rng.choice(["HDFC Bank", "Axis Bank", "SBI", "Amazon", "Airtel", "LIC"])
    ctx = dict(name=name, org=org, amount=rng.choice(AMOUNTS))
    turns = []
    for stage, text in template:
        turns.append({"speaker": "CALLER", "text": text.format(**ctx), "stage": stage, "victim_state": "NA"})
        turns.append({"speaker": "VICTIM", "text": rng.choice(VICTIM_REACTIONS[stage]),
                      "stage": stage, "victim_state": "CALM"})
    return {
        "seed": {
            "call_id": f"synth_benign_{idx:04d}",
            "is_scam": False,
            "archetype_id": f"benign_synth_{idx % len(BENIGN_CALLS)}",
            "archetype_name": "Legitimate call (synthetic)",
            "premise": "Genuine business call using overlapping vocabulary.",
            "victim": "Ordinary customer.",
            "style": "Composed benign template.",
            "language": "Romanised Hinglish.",
            "outcome": "no manipulation",
            "length": "short",
        },
        "source": "synthetic_stage_bank",
        "turns": turns,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scam-per-archetype", type=int, default=2)
    ap.add_argument("--benign", type=int, default=18)
    ap.add_argument("--seed", type=int, default=20260722)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    calls = []
    idx = 0
    for arch in ARCHETYPES:
        for _ in range(args.scam_per_archetype):
            idx += 1
            calls.append(make_scam_call(rng, idx, arch))
    for b in range(args.benign):
        calls.append(make_benign_call(rng, b, BENIGN_CALLS[b % len(BENIGN_CALLS)]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for c in calls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    scam = sum(1 for c in calls if c["seed"]["is_scam"])
    print(f"wrote {len(calls)} synthetic skeletons to {args.out} "
          f"({scam} scam / {len(calls) - scam} benign) across "
          f"{len(ARCHETYPES)} new scam archetypes")
    print("next: python paraphrase.py --no-llm  &&  python build_dataset.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
