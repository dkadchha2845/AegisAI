"""
The coercion index, as an agent.

**Why it exists.** It is the one signal in the engine that reads the *victim's*
side of the call. `engine/coercion.py` opens by saying why that independence
matters: derived from the stage labels it would be a restatement of the
classifier wearing a different hat, and fusing the two would be double-counting.
The ablation the paper wants is only meaningful because the two can disagree.

**What it consumes.** The victim's turns, from `conversation.py`.

**What it outputs.** The final index and its trend, the lexical feature counts
the tracker exposes, and one `victim_state` finding per victim turn — which is
what `threat_fusion` replays to charge the manipulation accumulator's compliance
and fear bars.

**How it connects.** `threat_fusion` reads `coercion_index` and replays the
victim states. Nothing reads the tracker itself; a fresh one is built per
investigation, because it is stateful across a call by design and sharing one
between two investigations would leak one citizen's stress into another's.

**How it is evaluated.** `test_inherited_agents.py` asserts the index equals the
one `analyze_text` reaches on the same input, and that a conversation with no
victim turns skips rather than reporting a calm victim.

**Limitations, stated.** Always text-only here, so the index is capped at
`TEXT_ONLY_CEILING` (72) and every result carries `coercion:text_only`. The
prosodic half — speech rate, pause ratio, pitch variance — comes from live ASR
word timings, which a batch investigation does not have; the ceiling exists so a
text-only stress estimate can never reach the same maximum as one backed by
audio. Task 6.2's streaming pipeline is what supplies the missing half.
"""

from __future__ import annotations

from typing import Dict, List

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState

from ...engine.coercion import CoercionTracker
from .. import registry
from ..base import AgentContext, Stage
from . import conversation, signals


@registry.register
class CoercionAgent:
    """Tracks victim stress across the conversation."""

    name = signals.COERCION_TRACKER
    version = "1.0.0"
    stage = Stage.REASON

    def can_handle(self, state: InvestigationState) -> bool:
        """Only when the victim actually said something.

        A forwarded SMS has no victim side, and answering "stress: 0" for it
        would be a measurement of nothing — `AgentStatus.SKIPPED` exists so 4.1
        can tell that from a calm victim. See the note in
        `inherited/__init__.py` about what the graph currently does with a skip.
        """
        return bool(conversation.victim_turns(state))

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        tracker = CoercionTracker()
        findings: List[Finding] = []
        features: Dict[str, float] = {}
        degraded: List[str] = []
        index = 0.0
        trend = "flat"

        for turn in conversation.victim_turns(state):
            out = tracker.observe(turn.text)
            index, trend = out.index, out.trend
            features = dict(out.features)
            for tag in out.degraded:
                if tag not in degraded:
                    degraded.append(tag)
            findings.append(
                Finding(
                    label=signals.F_VICTIM_STATE,
                    value=out.victim_state,
                    confidence=round(out.index / 100.0, 3),
                    source="coercion:lexical",
                    detail=str(turn.index),
                )
            )

        features[signals.K_COERCION_INDEX] = index
        features[signals.K_VICTIM_TURNS] = float(len(findings))

        return AgentResult(
            agent=self.name,
            version=self.version,
            # DEGRADED because the prosodic half of the signal is genuinely
            # absent, not because anything failed. The index is usable and
            # capped, and the caveat is visible rather than folded away.
            status=AgentStatus.DEGRADED if degraded else AgentStatus.OK,
            confidence=round(index / 100.0, 3),
            findings=[
                *findings,
                Finding(
                    label="coercion_trend",
                    value=trend,
                    confidence=1.0,
                    source="coercion:history",
                    detail=f"index {index:.1f}/100 over {len(findings)} victim turn(s)",
                ),
            ],
            features=features,
            provenance=["coercion:lexical"],
            error="; ".join(degraded) or None,
        )


__all__ = ["CoercionAgent"]
