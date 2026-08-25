"""
The names one adapter publishes and another reads.

**Why it exists.** `threat_fusion` and `digital_twin` run after the REASON tier
and rebuild their inputs from what that tier published. That makes a handful of
strings — `"coercion_index"`, `"peak_stage"` — a contract between modules, and
`agents/classify/agent.py` already states the rule this file follows: *a text
format between two modules is exactly what drifts silently*. Both sides import
the same constant, so a rename is a rename rather than a signal that quietly
stops arriving.

**What it consumes.** Nothing. It is names and two readers.

**What it outputs.** Feature keys, finding labels, and the small accessors that
turn `state.agent_results` back into values.

**How it connects.** Every adapter in this package imports it; the JUDGE-tier
ones use the accessors.

**How it is evaluated.** `test_inherited_agents.py` runs the whole graph and
asserts every key the fusion agent reads was actually published, so a producer
that stops emitting one fails a test rather than silently contributing zero.

**Limitations, stated.** `AgentResult.features` is `dict[str, float]`, so
anything categorical — a stage label, a check verdict, a script name — has to
travel as a `Finding` instead. That is why the readers below come in two
flavours, and why a stage is looked up by finding rather than by feature.
"""

from __future__ import annotations

from typing import List, Optional

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState

# --- agent names ------------------------------------------------------------

STAGE_CLASSIFIER = "stage_classifier"
COERCION_TRACKER = "coercion_tracker"
TRUST_PASSPORT = "trust_passport"
SCRIPT_MATCH = "script_match"
NUMBER_SPOOFING = "number_spoofing"
DIGITAL_TWIN = "digital_twin"
THREAT_FUSION = "threat_fusion"

# --- finding labels ---------------------------------------------------------

#: One per caller turn: `value` is the stage, `confidence` the classifier's.
F_STAGE = "stage"
#: The turn that drives the score — highest `classifier.stage_rank`.
F_PEAK_STAGE = "peak_stage"
#: One per victim turn: `value` is the victim state the coercion tracker read.
F_VICTIM_STATE = "victim_state"
#: Trust Passport checks, split by verdict so "which cases had a credential
#: request" is a label query rather than a scan. `value` is the check name.
F_PASSPORT_FAIL = "passport_fail"
F_PASSPORT_PASS = "passport_pass"
F_PASSPORT_UNKNOWN = "passport_unknown"
#: Caller-number checks, same split for the same reason.
F_NUMBER_FAIL = "number_fail"
F_NUMBER_PASS = "number_pass"
F_NUMBER_UNKNOWN = "number_unknown"
#: The closest scam-script template: `value` is its label, `confidence` the
#: similarity, `detail` the template itself so the citation is followable.
F_SCRIPT_MATCH = "script_match"
#: The Digital Twin's forecast: `value` is the predicted next stage.
F_NEXT_STAGE = "next_stage"
#: One per fused driver, and the band the score falls in.
F_THREAT_DRIVER = "threat_driver"
F_THREAT_LEVEL = "threat_level"

# --- feature keys -----------------------------------------------------------

K_COERCION_INDEX = "coercion_index"
K_TRUST_PCT = "trust_pct"
K_SPOOFING_RISK = "spoofing_risk"
K_SCRIPT_SIMILARITY = "script_similarity"
K_THREAT_SCORE = "threat_score"
K_STAGE_CONFIDENCE = "stage_confidence"
K_CALLER_TURNS = "caller_turns"
K_VICTIM_TURNS = "victim_turns"
K_PASSPORT_FAILS = "passport_fails"
K_NUMBER_FAILS = "number_fails"
K_FORECAST_PROBABILITY = "forecast_probability"
K_ETA_S = "eta_s"
K_ETA_TO_PAYMENT_S = "eta_to_payment_s"
#: The mean of the five bars. Deliberately *not* prefixed `manipulation_`: a
#: consumer that reads the tactic bars by prefix — which is how 4.1 will
#: assemble them — would otherwise pick the aggregate up as a sixth tactic
#: called "pressure". `threat.py` calls this quantity cumulative *tactic*
#: pressure, so the name is the engine's own rather than a new one.
K_TACTIC_PRESSURE = "tactic_pressure"

#: `ManipulationAccumulator.as_dict()` keys, prefixed. The bars are published by
#: `threat_fusion` rather than by `stage_classifier`, because the accumulator is
#: charged from *both* the caller's stages and the victim's states and only the
#: fusion agent has seen both.
MANIPULATION_PREFIX = "manipulation_"


def result_of(state: InvestigationState, agent: str) -> Optional[AgentResult]:
    """The most recent result from one agent, or None if it never ran.

    Last-wins rather than first, because the recursion bound in
    `AgentContext.max_depth` allows an agent to run again inside a
    sub-investigation, and the deeper answer is the more informed one.
    """
    found: Optional[AgentResult] = None
    for result in state.agent_results:
        if result.agent == agent:
            found = result
    return found


def answered(result: Optional[AgentResult]) -> bool:
    """Whether a result carries an answer at all.

    SKIPPED and ERROR do not. The distinction matters more here than anywhere
    else in the codebase: `threat.fuse` gives `trust_pct` and `spoofing_risk`
    Optional types precisely so an unrun check is not scored as a clean one, and
    collapsing "did not run" into 0.0 is how metadata manufactures a verdict.
    """
    return result is not None and result.status in (AgentStatus.OK, AgentStatus.DEGRADED)


def feature(result: Optional[AgentResult], key: str) -> Optional[float]:
    """One published feature, or None if the agent did not answer."""
    if not answered(result):
        return None
    assert result is not None  # narrowed by `answered`
    value = result.features.get(key)
    return float(value) if value is not None else None


def findings(result: Optional[AgentResult], label: str) -> List[Finding]:
    """Every finding an agent published under one label, in emission order."""
    if not answered(result):
        return []
    assert result is not None  # narrowed by `answered`
    return [f for f in result.findings if f.label == label]


def first_finding(result: Optional[AgentResult], label: str) -> Optional[Finding]:
    hits = findings(result, label)
    return hits[0] if hits else None


__all__ = [
    "COERCION_TRACKER",
    "DIGITAL_TWIN",
    "F_NEXT_STAGE",
    "F_NUMBER_FAIL",
    "F_NUMBER_PASS",
    "F_NUMBER_UNKNOWN",
    "F_PASSPORT_FAIL",
    "F_PASSPORT_PASS",
    "F_PASSPORT_UNKNOWN",
    "F_PEAK_STAGE",
    "F_SCRIPT_MATCH",
    "F_STAGE",
    "F_THREAT_DRIVER",
    "F_THREAT_LEVEL",
    "F_VICTIM_STATE",
    "K_CALLER_TURNS",
    "K_COERCION_INDEX",
    "K_ETA_S",
    "K_ETA_TO_PAYMENT_S",
    "K_FORECAST_PROBABILITY",
    "K_NUMBER_FAILS",
    "K_PASSPORT_FAILS",
    "K_SCRIPT_SIMILARITY",
    "K_SPOOFING_RISK",
    "K_STAGE_CONFIDENCE",
    "K_TACTIC_PRESSURE",
    "K_THREAT_SCORE",
    "K_TRUST_PCT",
    "K_VICTIM_TURNS",
    "MANIPULATION_PREFIX",
    "NUMBER_SPOOFING",
    "SCRIPT_MATCH",
    "STAGE_CLASSIFIER",
    "THREAT_FUSION",
    "TRUST_PASSPORT",
    "answered",
    "feature",
    "findings",
    "first_finding",
    "result_of",
]
