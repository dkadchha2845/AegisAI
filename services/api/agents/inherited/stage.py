"""
The stage classifier, as an agent.

**Why it exists.** Every other conversational signal is weighted by what the
caller is *doing* — `threat.fuse` gives the stage 40% of the four-signal sum,
the Digital Twin forecasts from it, and the manipulation accumulator is charged
by it. Without this adapter the graph has no access to any of that.

**What it consumes.** The caller's turns, from `conversation.py`.

**What it outputs.** One `stage` finding per caller turn — label, confidence and
which backend produced it — plus the `peak_stage`, chosen the same way
`analyze_text` chooses it: the turn with the highest
`threat_weight(stage) × confidence`, not the last one. A message that reaches
ISOLATION and then chats about the weather is still an isolation attempt.

**How it connects.** `threat_fusion` replays the stage findings to rebuild the
manipulation accumulator, and reads `peak_stage` as the stage to fuse on;
`digital_twin` forecasts from the same peak. Neither touches this module.

**How it is evaluated.** `test_inherited_agents.py` asserts the per-turn labels
and the peak match `analyze_text`'s `lines` and its chosen peak exactly, on the
same input. The model behind it is evaluated separately and honestly —
`/api/model/card` publishes the macro-F1 and states that the checkpoint is
trained but not promoted.

**Limitations, stated.** The wrapped model's limits are the model card's, not
this file's: 320 synthetic calls, Hinglish and English only, real-world transfer
unmeasured. What this adapter adds is one failure mode of its own — the
classifier costs **7.66 s on its first call and 22–34 ms after**, all of it
checkpoint loading, against an 8 s node budget. That is what `warmup()` is for,
and it is why `policy.py` gives this agent one attempt rather than two: a retry
of a model that is broken changes nothing and doubles the slowest node.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState

from ...engine import classifier as classifier_mod
from ...engine.classifier import load_classifier, threat_weight
from .. import registry
from ..base import AgentContext, Stage
from . import conversation, signals


@registry.register
class StageClassifierAgent:
    """Labels each caller turn with a stage of the scam arc."""

    name = signals.STAGE_CLASSIFIER
    version = "1.0.0"
    stage = Stage.REASON

    def can_handle(self, state: InvestigationState) -> bool:
        return conversation.has_caller_speech(state)

    async def warmup(self) -> None:
        """Pull the checkpoint into memory before any investigation waits on it.

        Not an optimisation. The measurement in `registry.warm_all` is that the
        first call costs 7.66 s against an 8 s budget, so an agent that loads
        lazily times out — or nearly does — for whoever happens to arrive first
        after a restart.
        """
        load_classifier()

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        classifier = load_classifier()
        findings: List[Finding] = []
        counts: Dict[str, float] = {}

        # `history` accumulates *both* speakers' text, exactly as the old path
        # feeds it. The classifier uses it for context, so dropping the victim's
        # turns would change the labels and break the equivalence this adapter
        # is measured on.
        history: List[str] = []
        peak: Optional[Finding] = None
        peak_rank = -1.0

        for turn in conversation.turns(state):
            if turn.speaker != conversation.CALLER:
                history.append(turn.text)
                continue
            prediction = classifier.predict(turn.text, history)
            history.append(turn.text)

            finding = Finding(
                label=signals.F_STAGE,
                value=prediction.label,
                confidence=round(prediction.confidence, 3),
                source=f"clf:{prediction.backend}",
                detail=str(turn.index),
            )
            findings.append(finding)
            counts[f"stage:{prediction.label}"] = counts.get(f"stage:{prediction.label}", 0.0) + 1.0

            rank = threat_weight(prediction.label) * prediction.confidence
            if rank > peak_rank:
                peak_rank, peak = rank, finding

        if peak is None:  # pragma: no cover - can_handle guarantees a caller turn
            return AgentResult(
                agent=self.name, version=self.version, status=AgentStatus.OK,
                confidence=0.0, provenance=[f"clf:{classifier.backend}"],
            )

        findings.append(
            Finding(
                label=signals.F_PEAK_STAGE,
                value=peak.value,
                confidence=peak.confidence,
                source=peak.source,
                detail=peak.detail,
            )
        )
        counts[signals.K_STAGE_CONFIDENCE] = peak.confidence
        counts[signals.K_CALLER_TURNS] = float(len(conversation.caller_turns(state)))

        # DEGRADED, not OK, when the lexical model is serving as a genuine
        # fallback — `serving_is_fallback` is the predicate classifier.py
        # defines for this question, and it is False when lexical is serving
        # because it *won* the measured comparison. Comparing `backend` to a
        # string instead is the bug /api/health was fixed for.
        degraded = classifier_mod.serving_is_fallback
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.DEGRADED if degraded else AgentStatus.OK,
            confidence=peak.confidence,
            findings=findings,
            features=counts,
            provenance=[f"clf:{classifier.backend}"],
            error="serving the lexical fallback; no promoted checkpoint" if degraded else None,
        )


__all__ = ["StageClassifierAgent"]
