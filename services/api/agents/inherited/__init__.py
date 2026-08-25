"""
The inherited KAVACH engine, as agents — task 1.7.

**Why it exists.** The engine in `services/api/engine/` is the reason this
project started with something rather than nothing: a stage classifier, threat
fusion, a coercion index, the Digital Twin, the Trust Passport, caller-number
spoofing checks and scam-script matching, all of it measured and covered by
tests that predate the agent layer. The graph built in 1.3 could not see any of
it. These seven adapters make it available to the graph **without rewriting a
line of it**, which is the whole constraint: a rewrite would produce cleaner
code and forfeit the only thing that makes the engine believable, which is that
it has been exercised.

**What they consume.** One `InvestigationState`. `conversation.py` is the single
place that decides what "the conversation" is for an investigation, so seven
adapters cannot disagree about it, and it delegates the actual parsing to
`engine/analyzer.normalise` — the same function the old path uses, so the two
paths see identical turns.

**What they output.** `AgentResult`, one per adapter, with findings and features
named in `signals.py`.

**How they connect.** Four run concurrently in the REASON tier over the same
text (`stage_classifier`, `coercion_tracker`, `trust_passport`, `script_match`);
`number_spoofing` runs earlier, in INVESTIGATE, because it works on metadata
rather than conversation; `threat_fusion` and `digital_twin` run last, in
JUDGE, because both need what the REASON tier published. A JUDGE-tier agent
reads `state.agent_results` — public output, never another agent's internals.

**How they are evaluated.** `test_inherited_agents.py`, and the bar is unusually
concrete: for the same input, the graph must produce **the same numbers as
`engine/analyzer.analyze_text`** — the same stage labels, the same manipulation
map, the same coercion index, the same trust percentage, the same script
similarity, and therefore the same fused score. An adapter that quietly
reimplemented something would show up as a difference.

**Limitations, stated.**

* `threat_fusion` does **not** write `state.risk_score`. It publishes the fused
  score as a feature and its drivers as findings, and stops there. The score in
  the contract belongs to task 4.6, which reconciles a calibrated model, the
  deterministic rules and the graph evidence; filling it here from a heuristic
  weighted sum would make an unearned claim in the field the report reads first.
* The dispositive-finding floor `analyze_text` applies on top of `fuse()` is
  likewise not reimplemented here. ARCHITECTURE.md §4 puts "deterministic rules
  — dispositive signals only" inside the fusion box, which is 4.6. The adapters
  publish the material those rules act on; applying them is 4.6's job, and
  duplicating the formula in two places is how the two paths start disagreeing.
* `number_spoofing` fires only when a phone number is actually available —
  `state.entities.phones`, or an evidence item the classifier typed as `PHONE`.
  Nothing populates `entities` yet, so on a transcript that merely *mentions* a
  number the agent SKIPs. Entity extraction (2.1/3.2) is what changes that.
* `digital_twin` requires a conversation, not an artefact. Forecasting the next
  stage of a one-line SMS is a forecast about a conversation that is not
  happening, and the twin was fitted on call arcs; it skips rather than answer.

Note on what a SKIP currently *is*
-----------------------------------
`can_handle` returning False makes `run_agent` produce
`AgentStatus.SKIPPED`, and `base.skipped()` says why that record matters: the
trace should show that an agent was considered and did not apply, and 4.1 has to
tell "ran and found nothing" from "never ran". The graph does not deliver that
today — `_run_stage` filters the tier through `registry.eligible()` first, so an
agent that cannot handle a state produces **no result at all** rather than a
SKIPPED one. That is a 1.3 behaviour this task surfaced rather than introduced,
it is recorded in `docs/TASKS.md`, and the shape of the fix belongs to 4.1,
which is the task whose stated need it serves. Until then, read the absence of
an agent from `agent_results` as the skip it is.

Why one package rather than seven agent directories
---------------------------------------------------
ARCHITECTURE.md §6 draws one directory per agent, and that is right for agents
that own a body of logic. These own none: each is a class, a `can_handle`, and
a call into a module that already existed. What they share is the property that
matters — *the code they wrap may not change* — so they are grouped by it, and
the shared `conversation.py` and `signals.py` sit where all seven can reach them
without a cross-agent import.
"""

from .coercion import CoercionAgent
from .fusion import ThreatFusionAgent
from .passport import TrustPassportAgent
from .script import ScriptMatchAgent
from .spoofing import NumberSpoofingAgent
from .stage import StageClassifierAgent
from .twin import DigitalTwinAgent

__all__ = [
    "CoercionAgent",
    "DigitalTwinAgent",
    "NumberSpoofingAgent",
    "ScriptMatchAgent",
    "StageClassifierAgent",
    "ThreatFusionAgent",
    "TrustPassportAgent",
]
