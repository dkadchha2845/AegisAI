"""
Caller-number spoofing intelligence, as an agent.

**Why it exists.** A digital-arrest call is carried as much by how the number
looks as by what is said on it. A real CBI officer does not cold-call from a
personal mobile, an Indian agency does not originate from a US country code,
and a number in the 1930 complaint feed is not a coincidence. It is the one
signal here that is metadata rather than conversation, which is why it sits in
the INVESTIGATE tier with the lookups rather than in REASON with the rest.

**What it consumes.** A phone number — from `state.entities.phones`, or from an
evidence item the 1.4 classifier typed `PHONE` — and the caller's own words as
the claimed identity.

**What it outputs.** One finding per check, split by verdict, plus
`spoofing_risk` on a 0–100 scale.

**How it connects.** `threat_fusion` reads `spoofing_risk` and hands it to
`threat.fuse`, where it rides as a *bounded escalator* on top of the four
conversational signals rather than taking weight from them — capped so a
spoofed number with a benign conversation tops out in HIGH and metadata alone
can never manufacture a CRITICAL.

**How it is evaluated.** `test_inherited_agents.py` asserts the risk and the
checks equal `analyze_number`'s on the same input, that a legitimate Indian
mobile with no authority claim does not FAIL anything, and — the one that
matters most — that when this agent SKIPs, fusion receives `None` rather than
`0.0`. `threat.fuse` gives `spoofing_risk` an Optional type precisely so an
absent number is not scored as a clean one.

**Limitations, stated.** No live reputation lookup, deliberately: a blocklist
this repository could bake in is stale before the demo, and a check the user
cannot reason about is one they are right to ignore.
`engine/reported_numbers.json` is a small, clearly synthetic sample so the
reported-number check has something to fire on; a deployment would sync it from
the DoT/TRAI and NCRB feeds.

The real limitation is upstream of this file: nothing populates
`state.entities` yet, so a number that merely appears *inside* a message does
not reach this agent — it has to arrive as its own evidence item. Scraping
identifiers out of text with a regex here would be a second, unowned
implementation of extraction; 2.1 and 3.2 are what close it properly. Until
then this agent skips more often than it should.

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
"""

from __future__ import annotations

from typing import Dict, List

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState

from ...engine.spoofing import analyze_number
from .. import registry
from ..base import AgentContext, Stage
from . import conversation, signals

_LABEL_BY_VERDICT = {
    "FAIL": signals.F_NUMBER_FAIL,
    "PASS": signals.F_NUMBER_PASS,
    "UNKNOWN": signals.F_NUMBER_UNKNOWN,
}


@registry.register
class NumberSpoofingAgent:
    """Scores the caller's number against what real institutions do."""

    name = signals.NUMBER_SPOOFING
    version = "1.0.0"
    stage = Stage.INVESTIGATE

    def can_handle(self, state: InvestigationState) -> bool:
        return bool(conversation.phone_numbers(state))

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        numbers = conversation.phone_numbers(state)
        claimed = conversation.claimed_identity_text(state) or None

        findings: List[Finding] = []
        worst = 0.0
        fails = 0

        for number in numbers:
            intel = analyze_number(number, claimed_identity=claimed)
            worst = max(worst, intel.risk)
            for check in intel.checks:
                if check.verdict == "FAIL":
                    fails += 1
                findings.append(
                    Finding(
                        label=_LABEL_BY_VERDICT[check.verdict],
                        value=check.name,
                        confidence=1.0 if check.verdict != "UNKNOWN" else 0.0,
                        source=check.source or "number_intel",
                        # The number is on the finding because an investigation
                        # may carry several, and "International routing" with no
                        # subject is a claim about nothing.
                        detail=f"{number}: {check.detail}",
                    )
                )

        features: Dict[str, float] = {
            # The worst number, not the mean: two numbers where one is reported
            # is a case with a reported number, and averaging would dilute the
            # finding that matters into the one that does not.
            signals.K_SPOOFING_RISK: round(worst, 1),
            signals.K_NUMBER_FAILS: float(fails),
        }
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.OK,
            confidence=round(worst / 100.0, 3),
            findings=findings,
            features=features,
            provenance=["number_intel", "reported_numbers.json"],
        )


__all__ = ["NumberSpoofingAgent"]
