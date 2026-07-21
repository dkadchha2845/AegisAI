"""
Unified fraud intelligence repository (FIGAE / Module 2, §4–5, Step 1).

The PDF's design: start with a historical fraud repository and grow it
continuously with real-time detections from Module 1. This module is that
repository.

  * `seed_cases()` builds a deterministic, clearly-synthetic historical set of
    Indian fraud cases with **intentional infrastructure reuse** — the same
    phone numbers, UPI IDs, and script templates recur across cases inside a
    campaign, so the graph in `graph.py` has real clusters to find rather than a
    scatter of disconnected nodes. It reproduces, among others, the courier /
    digital-arrest campaign the PDF exemplar (FC-021) describes.
  * `ingest_case_records()` turns saved Module 1 evidence packages (the
    `CaseRecord` rows Track 2 persists) into the same `FraudCase` shape, so a
    call detected live this morning is a node in the network this afternoon.

Everything is deterministic given the seed: a demo that regenerates the same
graph every boot is a demo that behaves the same on stage as in rehearsal.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .entities import extract_from_package
from .geo import CITIES

# --- the case record --------------------------------------------------------


@dataclass
class FraudCase:
    """One fraud case, normalised. The unit the whole engine operates on."""

    case_id: str
    source: str                      # "historical" | "module1"
    scam_type: str                   # archetype id (digital_arrest, courier_parcel…)
    threat_score: float              # 0-100
    threat_level: str                # CALM…CRITICAL
    amount_inr: float                # financial loss / attempted
    reported_at: str                 # ISO date
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    fake_authority: Optional[str] = None
    script_template: Optional[str] = None
    phones: List[str] = field(default_factory=list)
    upi_ids: List[str] = field(default_factory=list)
    wallets: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    bank_accounts: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- historical seed --------------------------------------------------------
# Each campaign is a "kit": a shared pool of infrastructure a single crew reuses
# across many victims. Instantiating N cases from one kit is what creates a
# detectable fraud cluster — which is the entire point of the module.

_CAMPAIGNS: List[Dict[str, Any]] = [
    {
        "id": "digital_arrest",
        "authority": "cbi",
        "script": "cbi-parcel-arrest-v3",
        "cities": ["Bengaluru", "Mysuru", "Hyderabad", "Warangal", "Chennai", "Coimbatore"],
        "phones": ["9845012371", "9845012372", "8067459921", "7042118830"],
        "upi_ids": ["cbi.verify@okaxis", "case.settle@okhdfcbank", "refund.node@okicici"],
        "count": 26,
        "loss": (180000, 4500000),
        "threat": (78, 97),
    },
    {
        "id": "courier_parcel",
        "authority": "fedex",
        "script": "fedex-customs-seizure-v2",
        "cities": ["Mumbai", "Pune", "Delhi", "Gurugram", "Bengaluru"],
        "phones": ["9930221145", "9930221146", "8080551200"],
        "upi_ids": ["fedex.clearance@oksbi", "customs.duty@okaxis"],
        "count": 18,
        "loss": (60000, 1200000),
        "threat": (70, 92),
    },
    {
        "id": "kyc_expiry",
        "authority": "rbi",
        "script": "bank-kyc-freeze-v1",
        "cities": ["Delhi", "Noida", "Lucknow", "Jaipur", "Ahmedabad"],
        "phones": ["7042990011", "7042990012", "9711002234"],
        "upi_ids": ["kyc.update@okhdfcbank", "verify.node@okaxis"],
        "count": 15,
        "loss": (20000, 400000),
        "threat": (58, 84),
    },
    {
        "id": "investment_returns",
        "authority": None,
        "script": "trading-group-payout-v4",
        "cities": ["Mumbai", "Surat", "Ahmedabad", "Kolkata", "Hyderabad"],
        "phones": ["9820773301", "9820773302", "8898120045", "9820773303"],
        "upi_ids": ["profit.desk@okicici", "withdraw.fee@oksbi", "vip.trade@okaxis"],
        "wallets": ["0x9f2A11c4B8e7D6f3a1c0E5b9D4f2A7c1B8e6D3a0"],
        "count": 14,
        "loss": (150000, 8000000),
        "threat": (62, 90),
    },
    {
        "id": "loan_app_harassment",
        "authority": None,
        "script": "loan-recovery-blackmail-v1",
        "cities": ["Gurugram", "Noida", "Bhopal", "Patna"],
        "phones": ["7003345512", "7003345513"],
        "upi_ids": ["settle.due@okpaytm", "recovery.node@okaxis"],
        "count": 11,
        "loss": (8000, 90000),
        "threat": (55, 80),
    },
    {
        "id": "electricity_bill",
        "authority": None,
        "script": "power-disconnect-tonight-v2",
        "cities": ["Kolkata", "Patna", "Bhubaneswar", "Visakhapatnam"],
        "phones": ["9007881122", "9007881123"],
        "upi_ids": ["bill.pay@okpaytm"],
        "count": 9,
        "loss": (2000, 60000),
        "threat": (50, 78),
    },
    {
        "id": "army_officer_olx",
        "authority": None,
        "script": "army-buyer-qr-v1",
        "cities": ["Jaipur", "Delhi", "Pune"],
        "phones": ["9660112233"],
        "upi_ids": ["army.advance@oksbi"],
        "count": 7,
        "loss": (5000, 120000),
        "threat": (48, 75),
    },
    {
        "id": "customs_duty",
        "authority": "customs",
        "script": "customs-gift-parcel-v1",
        "cities": ["Chennai", "Kochi", "Bengaluru"],
        "phones": ["7042118830", "9840223344"],  # 7042118830 shared with digital_arrest — a bridge crew
        "upi_ids": ["customs.duty@okaxis"],       # shared VPA with courier_parcel — same money mule
        "count": 8,
        "loss": (30000, 700000),
        "threat": (64, 88),
    },
]

_SCAM_NAMES = {
    "digital_arrest": "Digital arrest / CBI impersonation",
    "courier_parcel": "Courier parcel / customs seizure",
    "kyc_expiry": "Bank KYC expiry",
    "investment_returns": "Investment / trading group",
    "loan_app_harassment": "Instant loan app recovery",
    "electricity_bill": "Electricity disconnection",
    "army_officer_olx": "Armed-forces marketplace buyer",
    "customs_duty": "Customs duty payment",
    "sim_swap_trai": "TRAI / SIM disconnection",
    "refund_overpayment": "Refund overpayment",
    "job_offer_fee": "Work-from-home job fee",
    "unknown": "Unclassified",
}


def scam_name(scam_type: Optional[str]) -> str:
    return _SCAM_NAMES.get(scam_type or "unknown", (scam_type or "Unclassified").replace("_", " ").title())


def _level(score: float) -> str:
    if score >= 90:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "ELEVATED"
    if score >= 25:
        return "WATCH"
    return "CALM"


def seed_cases(seed: int = 20260721) -> List[FraudCase]:
    """The deterministic historical repository. Same output every call."""
    rng = random.Random(seed)
    base = datetime(2026, 1, 1)
    cases: List[FraudCase] = []
    n = 0

    for camp in _CAMPAIGNS:
        for _ in range(camp["count"]):
            n += 1
            city = rng.choice(camp["cities"])
            _, _, district, state = CITIES[city]
            score = round(rng.uniform(*camp["threat"]), 1)
            # Each case reuses a subset of the kit's infrastructure — not all of
            # it, so link-strength between two cases varies and centrality means
            # something. But every case draws from the shared pool, guaranteeing
            # the campaign is one connected component.
            phones = rng.sample(camp["phones"], k=min(len(camp["phones"]), rng.randint(1, 2)))
            upis = rng.sample(camp["upi_ids"], k=min(len(camp["upi_ids"]), rng.randint(1, 2)))
            wallets = list(camp.get("wallets", [])) if rng.random() < 0.4 else []
            cases.append(FraudCase(
                case_id=f"HFC-{n:04d}",
                source="historical",
                scam_type=camp["id"],
                threat_score=score,
                threat_level=_level(score),
                amount_inr=round(rng.uniform(*camp["loss"]), -2),
                reported_at=(base + timedelta(days=rng.randint(0, 200))).strftime("%Y-%m-%d"),
                city=city,
                district=district,
                state=state,
                fake_authority=camp["authority"],
                script_template=camp["script"],
                phones=phones,
                upi_ids=upis,
                wallets=wallets,
            ))

    # A handful of genuinely isolated cases — noise the clustering must NOT fold
    # into a campaign. A network engine that finds a campaign in everything is
    # one nobody trusts.
    for i in range(6):
        n += 1
        city = rng.choice(list(CITIES.keys()))
        _, _, district, state = CITIES[city]
        score = round(rng.uniform(45, 70), 1)
        cases.append(FraudCase(
            case_id=f"HFC-{n:04d}",
            source="historical",
            scam_type=rng.choice(["sim_swap_trai", "refund_overpayment", "job_offer_fee"]),
            threat_score=score,
            threat_level=_level(score),
            amount_inr=round(rng.uniform(3000, 200000), -2),
            reported_at=(base + timedelta(days=rng.randint(0, 200))).strftime("%Y-%m-%d"),
            city=city, district=district, state=state,
            phones=[f"9{rng.randint(100000000, 999999999)}"],
            upi_ids=[f"user{rng.randint(100, 999)}@okhdfcbank"],
        ))

    return cases


# --- Module 1 ingest --------------------------------------------------------


def case_from_package(
    package: Dict[str, Any], *, city: Optional[str] = None
) -> FraudCase:
    """Convert one Module 1 evidence package into a FraudCase.

    Location is not something Module 1 captures (a call has no postcode), so it
    is passed in when known — from the reporting citizen's city in Module 3, or
    left unset. Everything else is lifted from the package the engine already
    produced and can defend.
    """
    ent = extract_from_package(package)
    incident = package.get("incident", {}) or {}
    assess = package.get("assessment", {}) or {}
    call = package.get("call", {}) or {}
    geo = CITIES.get(city or "") if city else None

    # Peak stage → archetype-ish scam_type label. The package does not carry an
    # archetype id, so we map the incident type back to a coarse scam family.
    scam_type = _incident_to_scam(incident.get("type"), assess.get("claimed_identity"))
    score = float(incident.get("peak_threat") or 0.0)
    biggest_amount = max(ent.amounts, default=float(call.get("amount_inr") or 0.0))

    return FraudCase(
        case_id=package.get("report_id", "KVCH-UNKNOWN"),
        source="module1",
        scam_type=scam_type,
        threat_score=score,
        threat_level=incident.get("final_level") or _level(score),
        amount_inr=biggest_amount or 0.0,
        reported_at=(package.get("generated_at") or "")[:10] or datetime.utcnow().strftime("%Y-%m-%d"),
        city=city,
        district=geo[2] if geo else None,
        state=geo[3] if geo else None,
        fake_authority=(ent.authorities[0] if ent.authorities else None),
        script_template=None,
        phones=ent.phones,
        upi_ids=ent.upi_ids,
        emails=ent.emails,
        wallets=ent.wallets,
        bank_accounts=ent.bank_accounts,
        domains=ent.domains,
    )


def _incident_to_scam(incident_type: Optional[str], claimed: Optional[str]) -> str:
    it = (incident_type or "").lower()
    cl = (claimed or "").lower()
    if "digital arrest" in it or "cbi" in cl or "narcotics" in cl:
        return "digital_arrest"
    if "customs" in it or "customs" in cl or "parcel" in it:
        return "courier_parcel"
    if "kyc" in it or "rbi" in cl:
        return "kyc_expiry"
    if "credential" in it or "kyc" in it:
        return "kyc_expiry"
    if "transfer" in it:
        return "investment_returns"
    return "unknown"


def ingest_case_records(records: List[Dict[str, Any]]) -> List[FraudCase]:
    """Turn a list of persisted CaseRecord package_json blobs into FraudCases.
    Silently skips anything unparseable — one malformed saved case must not take
    down the whole intelligence view."""
    out: List[FraudCase] = []
    for rec in records:
        try:
            package = rec if isinstance(rec, dict) else json.loads(rec)
            out.append(case_from_package(package))
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
            continue
    return out
