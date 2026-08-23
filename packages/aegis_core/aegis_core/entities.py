"""
AegisAI — deterministic entity substitution for corpus expansion.

The first half of the paraphrase pipeline, and the half that cannot fail. It
swaps every name, city, bank, app, amount, and identifier in a gold call for a
fresh draw, before any model is involved.

Why this exists separately from the LLM rewrite
-----------------------------------------------
It gives guaranteed lexical diversity for free. A classifier trained on calls
that all say "Bank of Maharashtra, Kothrud branch" learns the branch name, not
the scam. Substitution alone produces a usable corpus even if every model and
API is unavailable, which is exactly the situation this project has been in.

Digits are randomised by regex; named entities come from explicit pools mapped
per variant, so "Deshmukh" becomes the same new surname everywhere in a call
rather than a different one per line. Consistency matters: a transcript where
the victim's name changes mid-call is not a transcript.
"""

from __future__ import annotations

import random
import re

# --- Pools ------------------------------------------------------------------

SURNAMES = [
    "Deshmukh", "Ranganathan", "Panchal", "Awasthi", "Tiwari", "Kulkarni",
    "Rathore", "Iyer", "Bhattacharya", "Chauhan", "Nair", "Sengupta",
    "Gaikwad", "Reddy", "Mohanty", "Bhandari", "Pillai", "Kaushik",
    "Vaidya", "Thakur", "Joshi", "Menon", "Rastogi", "Sodhi",
]

MALE_FIRST = [
    "Vasant", "Ramesh", "Mehul", "Nikhil", "Suresh", "Anil", "Pramod",
    "Kartik", "Devendra", "Harish", "Jayant", "Mukesh", "Sandeep", "Vivek",
]

FEMALE_FIRST = [
    "Aditi", "Sunita", "Priya", "Sanya", "Meera", "Kavita", "Shalini",
    "Rekha", "Anjali", "Deepa", "Nandini", "Poonam", "Swati", "Vandana",
]

CITIES = [
    "Mumbai", "Pune", "Bengaluru", "Surat", "Lucknow", "Bhopal", "Delhi",
    "Jaipur", "Indore", "Nagpur", "Kochi", "Patna", "Ranchi", "Guwahati",
    "Coimbatore", "Vadodara", "Ludhiana", "Visakhapatnam",
]

LOCALITIES = [
    "Kothrud", "Indiranagar", "Habibganj", "Andheri", "Salt Lake",
    "Banjara Hills", "Adyar", "Vaishali", "Gomti Nagar", "Aundh",
    "Malviya Nagar", "Rajouri Garden",
]

BANKS = [
    "Bank of Maharashtra", "Axis Bank", "ICICI Bank", "SBI", "HDFC Bank",
    "Canara Bank", "Punjab National Bank", "Kotak Mahindra Bank",
    "Union Bank", "IndusInd Bank", "Bank of Baroda", "Yes Bank",
]

UPI_APPS = ["Google Pay", "PhonePe", "Paytm", "BHIM", "Amazon Pay"]

REMOTE_APPS = ["AnyDesk", "TeamViewer", "QuickSupport", "RustDesk"]

COURIERS = ["FedEx", "DHL", "Blue Dart", "DTDC", "Aramex"]

ECOMM = ["Amazon", "Flipkart", "Myntra", "Meesho", "Ajio"]

AGENCIES = [
    "CBI", "Narcotics Control Bureau", "Enforcement Directorate",
    "Cyber Crime Cell", "Customs Department",
]

RANKS = [
    "sub-inspector", "inspector", "assistant commissioner",
    "deputy superintendent", "head constable",
]

# Gold-set value -> pool it should be drawn from. Longest strings first at
# substitution time so "Bank of Maharashtra" is not clipped by "Bank".
ENTITY_MAP: dict[str, list[str]] = {}
for pool in (
    SURNAMES, MALE_FIRST, FEMALE_FIRST, CITIES, LOCALITIES, BANKS,
    UPI_APPS, REMOTE_APPS, COURIERS, ECOMM, AGENCIES, RANKS,
):
    for value in pool:
        ENTITY_MAP[value] = pool


# --- Numeric patterns -------------------------------------------------------

_LONG_DIGITS = re.compile(r"\b\d{6,}\b")            # Aadhaar, account, codes
_COMMA_AMOUNT = re.compile(r"\b\d{1,3}(?:,\d{2,3})+\b")  # 4,50,000 / 22,000
_SHORT_NUM = re.compile(r"\b\d{2,5}\b")             # case ids, badge numbers
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_SPACED_DIGITS = re.compile(r"\b\d{4}(?: \d{4}){2,}\b")  # 4419 6620 8873


def _rand_digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def _sub_amount(rng: random.Random, match: re.Match) -> str:
    """Replace an amount with a plausible different one of similar magnitude."""
    digits = match.group(0).replace(",", "")
    magnitude = len(digits)
    lo, hi = 10 ** (magnitude - 1), 10**magnitude - 1
    value = rng.randint(lo, hi)
    # Round to something a human would actually say.
    step = 1000 if magnitude >= 5 else 100
    value = max(step, (value // step) * step)
    s = str(value)
    # Indian grouping: last 3, then pairs.
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def substitute(turns: list[dict], rng: random.Random) -> list[dict]:
    """
    Return a copy of `turns` with all entities and numbers swapped.

    A single mapping is built per call and applied to every turn, so an entity
    keeps its new identity throughout the transcript.
    """
    corpus = " ".join(t["text"] for t in turns)

    # Build one consistent replacement per entity actually present.
    mapping: dict[str, str] = {}
    for value, pool in ENTITY_MAP.items():
        if re.search(rf"\b{re.escape(value)}\b", corpus):
            choices = [c for c in pool if c != value] or pool
            mapping[value] = rng.choice(choices)

    # Longest first: "Bank of Maharashtra" must be replaced before "Bank".
    ordered = sorted(mapping.items(), key=lambda kv: -len(kv[0]))

    out = []
    for turn in turns:
        text = turn["text"]
        for old, new in ordered:
            text = re.sub(rf"\b{re.escape(old)}\b", new, text)

        text = _SPACED_DIGITS.sub(
            lambda m: " ".join(
                _rand_digits(rng, len(p)) for p in m.group(0).split()
            ),
            text,
        )
        text = _IFSC.sub(
            lambda m: rng.choice(["HDFC", "ICIC", "SBIN", "UTIB", "PUNB"])
            + "0"
            + _rand_digits(rng, 6),
            text,
        )
        text = _COMMA_AMOUNT.sub(lambda m: _sub_amount(rng, m), text)
        text = _LONG_DIGITS.sub(lambda m: _rand_digits(rng, len(m.group(0))), text)
        text = _SHORT_NUM.sub(
            lambda m: _rand_digits(rng, len(m.group(0))).lstrip("0")
            or _rand_digits(rng, 1),
            text,
        )

        out.append({**turn, "text": text})
    return out
