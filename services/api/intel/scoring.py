"""
Fraud risk scoring engine (FIGAE / Module 2, §6).

Each cluster gets a dynamic risk score from the six factors the PDF names:
number of linked cases, financial loss, reused infrastructure, geographic spread,
Module 1 threat scores, and network connectivity. The weights live in one table,
the same discipline as `engine/threat.py`: a score you can read the composition
of, not a black box.

Bands: LOW / MEDIUM / HIGH / CRITICAL, exactly as the PDF specifies.
"""

from __future__ import annotations

import math
from typing import Tuple

# Each factor is squashed to 0-1 then weighted; the weights sum to 1.0. Loss and
# case-count use a log/saturating curve because the difference between 2 and 20
# linked cases matters far more than between 200 and 220.
_W_CASES = 0.22        # how many victims this crew has reached
_W_LOSS = 0.24         # rupees actually at risk — the business impact axis
_W_INFRA = 0.20        # reused phones/UPIs/wallets — the sign of an operation
_W_SPREAD = 0.14       # states touched — a cross-jurisdiction case is worse
_W_THREAT = 0.12       # Module 1's own peak threat on the linked calls
_W_CONNECT = 0.08      # mean threat, a proxy for how tightly the cases rhyme


def _sat(x: float, half: float) -> float:
    """Saturating curve: 0 at 0, 0.5 at `half`, →1 as x grows. Keeps a runaway
    factor (one €80-lakh loss) from pinning the whole score on its own."""
    if x <= 0:
        return 0.0
    return x / (x + half)


def score_cluster(
    *,
    n_cases: int,
    total_loss: float,
    shared_infra: int,
    n_states: int,
    peak_threat: float,
    mean_threat: float,
) -> Tuple[float, str]:
    """Return (0-100 risk score, band). Pure function of the six factors."""
    cases_c = _sat(n_cases, 8)              # ~0.5 at 8 linked cases
    loss_c = _sat(total_loss, 2_000_000)    # ~0.5 at ₹20 lakh
    infra_c = _sat(shared_infra, 4)         # ~0.5 at 4 shared identifiers
    spread_c = _sat(n_states, 2)            # ~0.5 at 2 states, →1 by 6
    threat_c = max(0.0, min(1.0, peak_threat / 100.0))
    connect_c = max(0.0, min(1.0, mean_threat / 100.0))

    raw = (
        _W_CASES * cases_c
        + _W_LOSS * loss_c
        + _W_INFRA * infra_c
        + _W_SPREAD * spread_c
        + _W_THREAT * threat_c
        + _W_CONNECT * connect_c
    )
    score = round(100.0 * raw, 1)
    return score, band(score)


def band(score: float) -> str:
    if score >= 72:
        return "CRITICAL"
    if score >= 55:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def factor_breakdown(
    *,
    n_cases: int,
    total_loss: float,
    shared_infra: int,
    n_states: int,
    peak_threat: float,
    mean_threat: float,
) -> list[dict]:
    """The named contributions behind a cluster's risk score, so the investigator
    dashboard can answer 'why is this CRITICAL?' — the same provenance rule the
    threat meter follows."""
    factors = [
        ("Linked cases", _W_CASES * _sat(n_cases, 8), f"{n_cases} cases connected"),
        ("Financial loss", _W_LOSS * _sat(total_loss, 2_000_000),
         f"₹{total_loss:,.0f} at risk"),
        ("Reused infrastructure", _W_INFRA * _sat(shared_infra, 4),
         f"{shared_infra} shared identifiers"),
        ("Geographic spread", _W_SPREAD * _sat(n_states, 2), f"{n_states} states"),
        ("Module 1 peak threat", _W_THREAT * (peak_threat / 100.0),
         f"peak {peak_threat:.0f}/100"),
        ("Network connectivity", _W_CONNECT * (mean_threat / 100.0),
         f"mean {mean_threat:.0f}/100"),
    ]
    return [
        {"factor": name, "contribution": round(contrib, 3), "detail": detail}
        for name, contrib, detail in sorted(factors, key=lambda f: -f[1])
    ]
