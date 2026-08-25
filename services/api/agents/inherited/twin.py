"""
The Digital Twin, as an agent.

**Why it exists.** Every other signal here describes what has already happened.
This one answers the two questions a defender can actually act on — *what will
the scammer do next*, and *how long until money moves if nobody intervenes* —
from a first-order Markov model fitted over collapsed stage runs.

**What it consumes.** The `peak_stage` the classifier published. Nothing else;
the twin is a lookup over a fitted matrix.

**What it outputs.** The forecast next stage with its probability, the seconds
to it, and the seconds to payment.

**How it connects.** JUDGE tier, alongside `threat_fusion`, because both need
the REASON tier's output and neither needs the other's.

**How it is evaluated.** `test_inherited_agents.py` asserts the forecast equals
`DigitalTwin().forecast()` on the same stage, that a single-line artefact skips
rather than forecasting, and that a missing fitted matrix degrades to the
prior rather than failing.

**Limitations, stated.** Two, and the first is a scope limit rather than a
defect. *The twin forecasts conversations.* It was fitted on call arcs, and
"what will the scammer say next" is a question about a scam that is still
running; asked of a forwarded one-line SMS it is a forecast about a conversation
that is not happening. So this agent requires a real exchange — a transcript, or
at least two caller turns — and skips otherwise, rather than answering zero.

Second, the model's own limits, quoted rather than softened: the matrix is
first-order over collapsed runs, the ETA is a **median** turn count converted at
a measured 12 s per turn (a mean is dragged into uselessness by calls that
meander for forty turns), and stages with fewer than `MIN_SUPPORT` fitted
samples have no timing quoted at all. Without the fitted file on disk the twin
still answers from the canonical arc as a uniform prior and reports
`twin:prior_only`, which this adapter surfaces as DEGRADED.
"""

from __future__ import annotations

from typing import Dict

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState

from ...engine.twin import DigitalTwin
from .. import registry
from ..base import AgentContext, Stage
from . import conversation, signals

#: Below this the evidence is an artefact, not an exchange. Two caller turns is
#: the smallest thing that has a "next".
MIN_CALLER_TURNS = 2


@registry.register
class DigitalTwinAgent:
    """Forecasts the next stage of a scam in progress, and the time to money."""

    name = signals.DIGITAL_TWIN
    version = "1.0.0"
    stage = Stage.JUDGE

    def can_handle(self, state: InvestigationState) -> bool:
        if not signals.answered(signals.result_of(state, signals.STAGE_CLASSIFIER)):
            return False
        if state.transcript is not None and state.transcript.final:
            return True
        return len(conversation.caller_turns(state)) >= MIN_CALLER_TURNS

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        twin = DigitalTwin()
        peak = signals.first_finding(
            signals.result_of(state, signals.STAGE_CLASSIFIER), signals.F_PEAK_STAGE
        )
        stage = peak.value if peak and peak.value else "BENIGN"

        # `since_s` is 0: a batch investigation has no clock running inside the
        # conversation. The live path passes real elapsed time, which is what
        # makes "42 seconds to the next stage" mean something there and a
        # dwell-length estimate here.
        forecast = twin.forecast(stage, since_s=0.0)

        features: Dict[str, float] = {
            signals.K_FORECAST_PROBABILITY: forecast.probability,
            signals.K_ETA_S: forecast.eta_s,
        }
        if forecast.eta_to_payment_s is not None:
            features[signals.K_ETA_TO_PAYMENT_S] = forecast.eta_to_payment_s

        detail = f"from {stage}; ~{forecast.eta_s:.0f}s away"
        if forecast.eta_to_payment_s is not None:
            detail += f", ~{forecast.eta_to_payment_s:.0f}s to a payment demand"

        degraded = list(twin.degraded)
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.DEGRADED if degraded else AgentStatus.OK,
            confidence=forecast.probability,
            findings=[
                Finding(
                    label=signals.F_NEXT_STAGE,
                    value=forecast.next_stage,
                    confidence=forecast.probability,
                    source="twin:markov" if not degraded else "twin:prior",
                    detail=detail,
                )
            ],
            features=features,
            provenance=["twin:transitions" if not degraded else "twin:canonical_prior"],
            error="; ".join(degraded) or None,
        )


__all__ = ["MIN_CALLER_TURNS", "DigitalTwinAgent"]
