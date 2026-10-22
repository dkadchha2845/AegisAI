"""
The feature-assembly contract, version 0 (T-19, legacy 4.1).

**Why it exists.** The judge must read a typed, deterministic vector, not the
internals of eight agents. Until now each agent wrote whatever keys it liked
into `AgentResult.features`, and the provisional judge (T-20) reached into
them by name. This registry declares every feature an agent emits — its name,
type, range, the agent that produces it, and what an absence means — and
`assemble()` turns a state into `state.risk_features` from those declarations
alone.

**What it consumes.** `state.agent_results`, and nothing else.

**What it outputs.** `risk_features`: one entry per declared *input* feature,
in declaration order, as a float or `None`. `None` means **missing** — the agent
that produces it was skipped, errored or never ran — and is never written as
zero, because zero is a measurement and a skipped agent measured nothing
(`AgentStatus` says SKIPPED "must never be read as clean").

**The null policy, precisely.**

* The producing agent did not answer (absent, SKIPPED, ERROR) → every one of
  its features is `None`.
* It answered (OK or DEGRADED) but did not emit the key → the declaration's
  `absent` rule: `zero` for counts (a stage never predicted was predicted
  zero times), `missing` where absence means "not measurable here" (prosody
  without audio, a time-to-payment with no path to payment).
* DEGRADED is *not* missing. The contract defines it as "answered from a
  fallback — the answer is usable and the shortfall is visible", and the
  coercion agent is DEGRADED on every text investigation for want of audio:
  treating its index as missing would discard it on every case.

**Roles.** `input` features form the vector. `output` features are produced by
the judge tier (the provisional judge's scores, the Digital Twin's forecast):
declared, so nothing emitted is undeclared, but never assembled — a judge must
not read its own output.

**How it connects.** The graph runs `assemble()` as its own node between the
reason and judge tiers (`orchestration/graph.py`), so every input agent has
answered and no judge has. The registry is versioned by `SCHEMA_SHA256`; a test
fails when the declarations change and the hash does not.

**How it is evaluated.** `test_features.py`: every feature any agent emits on
the fixtures is declared; missing is `None`, never zero; the same state gives
the same vector; the drift guard; values fall inside their declared ranges.

**Limitations.** Version 0 covers today's agents only. Features from agents
that do not exist yet (URL, threat intel, graph) are added with those agents.
Ranges are declared, and asserted on fixtures; they are not enforced at run
time, where an out-of-range value would be passed through rather than hidden.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Literal, Optional

from schema.models import AgentStatus, InputType, InvestigationState

#: Bumped by hand when a declaration changes meaning; the hash below catches
#: the change being made without anyone deciding that.
SCHEMA_VERSION = 0

Role = Literal["input", "output"]
Absent = Literal["zero", "missing"]


@dataclass(frozen=True)
class Feature:
    name: str
    agent: str
    dtype: Literal["int", "float"]
    low: float
    #: None = unbounded above (a count, a duration).
    high: Optional[float]
    #: What it means when the agent answered but did not emit the key.
    absent: Absent
    role: Role
    description: str


def _f(name: str, agent: str, dtype: str, low: float, high: Optional[float],
       absent: str, description: str, role: str = "input") -> Feature:
    return Feature(name, agent, dtype, low, high, absent, role, description)  # type: ignore[arg-type]


# The stage labels and entity kinds are listed here rather than imported, so
# that adding a label elsewhere changes this schema only when someone declares
# it — and the "undeclared feature" test says so the moment an agent emits it.
_STAGES = (
    "GREETING", "AUTHORITY_CLAIM", "FEAR_INDUCTION", "ISOLATION",
    "VERIFICATION_DEMAND", "PAYMENT_SETUP", "PAYMENT_EXECUTION", "BENIGN",
)
_ENTITY_KINDS = (
    "phones", "upi_ids", "emails", "wallets", "bank_accounts", "domains", "urls",
    "authorities", "banks", "locations", "scam_keywords", "amounts",
)
_TACTICS = ("authority", "fear", "isolation", "urgency", "compliance")


def _declarations() -> List[Feature]:
    out: List[Feature] = []
    # --- classify ------------------------------------------------------------
    for input_type in InputType:
        out.append(_f(f"input_type:{input_type.value}", "input_classifier", "int", 0, None, "zero",
                      f"evidence items detected as {input_type.value}"))
    out.append(_f("type_conflicts", "input_classifier", "int", 0, None, "zero",
                  "items whose declared type contradicts their bytes"))
    # --- extract -------------------------------------------------------------
    for kind in _ENTITY_KINDS:
        out.append(_f(f"entities_{kind}", "entity_extractor", "int", 0, None, "zero",
                      f"distinct {kind.replace('_', ' ')} found in the evidence"))
    # --- reason --------------------------------------------------------------
    for label in _STAGES:
        out.append(_f(f"stage:{label}", "stage_classifier", "int", 0, None, "zero",
                      f"caller turns classified {label}"))
    out += [
        _f("stage_confidence", "stage_classifier", "float", 0, 1, "missing",
           "classifier confidence on the peak stage"),
        _f("caller_turns", "stage_classifier", "int", 0, None, "zero", "caller turns classified"),
        _f("coercion_index", "coercion_tracker", "float", 0, 100, "missing",
           "victim coercion index, 0-100"),
        _f("victim_turns", "coercion_tracker", "int", 0, None, "zero", "victim turns read"),
        _f("compliance_hits", "coercion_tracker", "int", 0, None, "zero",
           "victim turns showing compliance"),
        _f("resistance_hits", "coercion_tracker", "int", 0, None, "zero",
           "victim turns showing resistance"),
        _f("distress_hits", "coercion_tracker", "int", 0, None, "zero",
           "victim turns showing distress"),
        _f("speech_rate_wpm", "coercion_tracker", "float", 0, None, "missing",
           "victim speech rate; audio only"),
        _f("pause_ratio", "coercion_tracker", "float", 0, 1, "missing",
           "share of victim audio that is silence; audio only"),
        _f("pitch_var", "coercion_tracker", "float", 0, None, "missing",
           "victim pitch variance; audio only"),
        _f("trust_pct", "trust_passport", "float", 0, 100, "missing",
           "share of resolved identity checks passed"),
        _f("passport_fails", "trust_passport", "int", 0, None, "zero", "identity checks failed"),
        _f("script_similarity", "script_match", "float", 0, 1, "missing",
           "closest scam-script template similarity"),
        _f("spoofing_risk", "number_spoofing", "float", 0, 100, "missing",
           "worst caller-number spoofing risk"),
        _f("number_fails", "number_spoofing", "int", 0, None, "zero", "caller-number checks failed"),
    ]
    # --- judge (outputs: declared, never assembled) ---------------------------
    out += [
        _f("threat_score", "threat_fusion", "float", 0, 100, "missing",
           "fused score before the dispositive floor", "output"),
        _f("risk_score", "threat_fusion", "float", 0, 100, "missing",
           "provisional score after the floor (T-20)", "output"),
        _f("tactic_pressure", "threat_fusion", "float", 0, 1, "missing",
           "mean of the five manipulation bars", "output"),
    ]
    for tactic in _TACTICS:
        out.append(_f(f"manipulation_{tactic}", "threat_fusion", "float", 0, 1, "missing",
                      f"{tactic} manipulation pressure", "output"))
    out += [
        _f("forecast_probability", "digital_twin", "float", 0, 1, "missing",
           "probability of the forecast next stage", "output"),
        _f("eta_s", "digital_twin", "float", 0, None, "missing",
           "seconds to the next stage", "output"),
        _f("eta_to_payment_s", "digital_twin", "float", 0, None, "missing",
           "seconds to a payment demand; absent with no path to one", "output"),
    ]
    return out


FEATURES: tuple[Feature, ...] = tuple(_declarations())
BY_NAME: Dict[str, Feature] = {f.name: f for f in FEATURES}
INPUTS: tuple[Feature, ...] = tuple(f for f in FEATURES if f.role == "input")

#: The committed fingerprint of the declarations. Change a declaration and the
#: test that recomputes this fails until it is updated here — in the same diff,
#: where a reviewer sees both.
SCHEMA_SHA256 = "af93eca3e521f456c9b5ca025e2b38bfc6319a9dd66ac59520c96d9c1bb3c593"


def schema_digest(features: Iterable[Feature] = FEATURES) -> str:
    canonical = json.dumps(
        {"version": SCHEMA_VERSION, "features": [asdict(f) for f in features]},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_ANSWERED = (AgentStatus.OK, AgentStatus.DEGRADED)


def assemble(state: InvestigationState) -> Dict[str, Optional[float]]:
    """The input vector for this state: every declared input, in order.

    A pure function of `state.agent_results`. When an agent ran more than once
    (a retried node records each attempt), its last result counts — the one
    the rest of the graph saw.
    """
    latest = {r.agent: r for r in state.agent_results}
    vector: Dict[str, Optional[float]] = {}
    for feature in INPUTS:
        result = latest.get(feature.agent)
        if result is None or result.status not in _ANSWERED:
            vector[feature.name] = None
            continue
        value = result.features.get(feature.name)
        if value is None:
            vector[feature.name] = 0.0 if feature.absent == "zero" else None
        else:
            vector[feature.name] = float(value)
    return vector


__all__ = [
    "BY_NAME",
    "FEATURES",
    "INPUTS",
    "SCHEMA_SHA256",
    "SCHEMA_VERSION",
    "Feature",
    "assemble",
    "schema_digest",
]
