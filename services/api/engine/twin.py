"""
The Digital Twin — forecasting the next stage and the time to money.

Loads the transition matrix and dwell statistics that `ml/build_dataset.py`
fits from the corpus, and answers two questions on every frame:

    "what will the scammer do next, and how sure are we?"
    "how long until money moves if nobody intervenes?"

Two things worth knowing about the model
----------------------------------------

**The matrix is fitted on collapsed stage runs.** A scammer spends several
turns inside one stage, so a raw turn-to-turn matrix is ~85% self-transitions
and the forecast would read "NEXT: ISOLATION" while already in ISOLATION.
build_dataset.py collapses runs before counting, so the answer is genuinely
"what comes *after* this".

**The ETA is median turns, not mean.** Turn counts to payment are heavily
right-skewed — a handful of calls meander for forty turns — and a mean ETA is
dragged into uselessness by them. The median is the number a defender can act
on. It is converted to seconds with a measured seconds-per-turn constant.

If the fitted file is missing the twin still answers, using the canonical
stage order as a uniform prior, and reports `degraded=["twin:prior_only"]`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import settings

#: Median seconds per conversational turn, measured across the corpus. Used to
#: turn "3 turns to payment" into "≈36 seconds".
SECONDS_PER_TURN = 12.0

#: Minimum fitted samples before a stage's timing is quoted at all. The corpus
#: report already warns that ISOLATION and VERIFICATION_DEMAND are thin; this
#: keeps a four-sample median from being read out as fact.
MIN_SUPPORT = 20

CANONICAL_ORDER = [
    "GREETING", "AUTHORITY_CLAIM", "FEAR_INDUCTION", "ISOLATION",
    "VERIFICATION_DEMAND", "PAYMENT_SETUP", "PAYMENT_EXECUTION",
]

#: Fallback prior when no fitted matrix is on disk: each stage most likely
#: advances one step along the canonical arc.
_PRIOR = {
    stage: {CANONICAL_ORDER[min(i + 1, len(CANONICAL_ORDER) - 1)]: 0.7}
    for i, stage in enumerate(CANONICAL_ORDER)
}
_PRIOR["BENIGN"] = {"BENIGN": 0.9}


@dataclass
class ForecastOut:
    next_stage: str
    probability: float
    eta_s: float
    eta_to_payment_s: float | None
    last_prediction_correct: bool | None = None


class DigitalTwin:
    def __init__(self, path: Path | None = None):
        self.path = path or settings.twin_path
        self.transitions: dict[str, dict[str, float]] = dict(_PRIOR)
        self.dwell_turns: dict[str, float] = {}
        self.turns_to_payment: dict[str, float] = {}
        #: Fitted sample count per stage, so the UI can show how well-evidenced
        #: an ETA is instead of presenting every number with equal authority.
        self.support: dict[str, int] = {}
        self.degraded: list[str] = []
        self._load()
        # Scored forecasting: remember what we predicted so `FORECAST_HIT`
        # can fire when it comes true. A forecast nobody scores is a guess.
        self._pending: tuple[str, str] | None = None  # (from_stage, predicted)
        self.hits = 0
        self.misses = 0

    def _load(self) -> None:
        if not self.path.exists():
            self.degraded.append("twin:prior_only")
            return
        try:
            blob = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            self.degraded.append("twin:prior_only")
            return
        if not isinstance(blob, dict):
            self.degraded.append("twin:prior_only")
            return

        matrix = blob.get("matrix") or {}
        if matrix:
            self.transitions = {
                src: {dst: float(p) for dst, p in row.items()}
                for src, row in matrix.items()
                if isinstance(row, dict)
            }

        # `dwell_turns` and `eta_to_payment` are distributions, not scalars —
        # each stage carries {median, n} so a stage fitted on four calls can
        # be told apart from one fitted on a hundred. Sample counts below
        # MIN_SUPPORT are dropped rather than quoted: an ETA derived from
        # three examples is a number the deck cannot defend.
        for stage, entry in (blob.get("dwell_turns") or {}).items():
            if isinstance(entry, dict) and entry.get("n", 0) >= MIN_SUPPORT:
                self.dwell_turns[stage] = float(entry["median"])
        for stage, entry in (blob.get("eta_to_payment") or {}).items():
            if isinstance(entry, dict) and entry.get("n", 0) >= MIN_SUPPORT:
                self.turns_to_payment[stage] = float(entry["median_turns"])
                self.support[stage] = int(entry["n"])

    # -- forecasting -------------------------------------------------------

    def forecast(self, stage: str, since_s: float = 0.0) -> ForecastOut:
        row = self.transitions.get(stage) or _PRIOR.get(stage, {})
        if not row:
            next_stage, probability = "BENIGN", 0.3
        else:
            next_stage, probability = max(row.items(), key=lambda kv: kv[1])

        # Time to the next stage = expected dwell minus time already spent.
        # Clamped at 3s: "0 seconds away" reads as broken, not urgent.
        dwell = self.dwell_turns.get(stage, 2.5) * SECONDS_PER_TURN
        eta_s = max(3.0, dwell - since_s)

        eta_payment: float | None = None
        turns = self.turns_to_payment.get(stage)
        if turns is not None:
            eta_payment = max(0.0, turns * SECONDS_PER_TURN - since_s)
        elif stage in CANONICAL_ORDER and stage != "PAYMENT_EXECUTION":
            # No fitted number for this stage — fall back to counting the
            # remaining arc, which is crude but never silently absent.
            remaining = len(CANONICAL_ORDER) - 1 - CANONICAL_ORDER.index(stage)
            eta_payment = max(0.0, remaining * 3 * SECONDS_PER_TURN - since_s)

        self._pending = (stage, next_stage)
        return ForecastOut(
            next_stage=next_stage,
            probability=round(min(1.0, probability), 3),
            eta_s=round(eta_s, 1),
            eta_to_payment_s=round(eta_payment, 1) if eta_payment is not None else None,
        )

    def score_transition(self, from_stage: str, to_stage: str) -> bool | None:
        """Called when the stage actually changes. Returns whether the twin
        called it, or None if there was no live prediction to score."""
        if self._pending is None or self._pending[0] != from_stage:
            return None
        correct = self._pending[1] == to_stage
        if correct:
            self.hits += 1
        else:
            self.misses += 1
        self._pending = None
        return correct

    @property
    def accuracy(self) -> float | None:
        total = self.hits + self.misses
        return round(self.hits / total, 3) if total else None
