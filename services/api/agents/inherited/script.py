"""
Scam-script template matching, as an agent.

**Why it exists.** Digital-arrest calls are run from a script. The words vary —
one caller says "narcotics", another "money laundering" — but the sentences are
near-duplicates of a small set of templates, and measuring that is a signal a
keyword list cannot produce: a paraphrase that shares no rare word with the
template still scores high. It is also the most directly explainable signal the
engine has, because the matched template can be shown next to the caller's line.

**What it consumes.** The caller's turns, from `conversation.py`.

**What it outputs.** The strongest match across the conversation — its
similarity, the template's label, and the template text — plus
`script_similarity` as a feature.

**How it connects.** `threat_fusion` reads the similarity and the label and
passes both to `threat.fuse`, which gates the contribution at `SCRIPT_MIN`
(0.45) so shared-vocabulary coincidence in an ordinary call fires nothing.

**How it is evaluated.** `test_inherited_agents.py` asserts the similarity
equals the maximum `analyze_text` reaches over the same turns. The matcher
itself is evaluated in `test_scripts.py`, and its backend choice is a
measurement rather than a default: dense cosine over all-MiniLM-L6-v2 scored a
benign Hinglish line at 0.707 against a real authority-claim line at 0.686, so
no threshold preserved the false-positive discipline, while TF-cosine keeps
benign under 0.2 and scam templates over 0.5.

**Limitations, stated.** Twelve templates, two per manipulation beat, English
and Hinglish. A script this project has never seen scores low, so a low
similarity is not evidence of legitimacy — which is exactly why `fuse` treats it
as a bounded escalator that can only ever add. Dense matching stays available
behind `AEGIS_DENSE_SCRIPTS=1` for the day a multilingual embedding model is
measured to win, under the same promotion-by-evidence rule as the checkpoint.
"""

from __future__ import annotations

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState

from ...engine.scripts import get_script_matcher
from .. import registry
from ..base import AgentContext, Stage
from . import conversation, signals


@registry.register
class ScriptMatchAgent:
    """How close the caller's lines are to a known scam script."""

    name = signals.SCRIPT_MATCH
    version = "1.0.0"
    stage = Stage.REASON

    def can_handle(self, state: InvestigationState) -> bool:
        return conversation.has_caller_speech(state)

    async def warmup(self) -> None:
        """Build the matcher up front.

        Nearly free today — twelve templates and a token count. It is here for
        the day `AEGIS_DENSE_SCRIPTS=1` is measured to win, at which point the
        first call becomes an embedding-model load inside an 8 s node budget,
        which is the shape of failure this project has already been bitten by
        twice.
        """
        get_script_matcher()

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        matcher = get_script_matcher()
        best = None
        best_turn = -1

        # The maximum across the conversation, not the last line's — the same
        # choice `analyze_text` makes, and for the same reason the peak stage is
        # taken rather than the final one: one line reciting the arrest script is
        # the finding, whatever was said afterwards.
        for turn in conversation.caller_turns(state):
            match = matcher.match(turn.text)
            if best is None or match.similarity > best.similarity:
                best, best_turn = match, turn.index

        if best is None:  # pragma: no cover - can_handle guarantees a caller turn
            return AgentResult(
                agent=self.name, version=self.version,
                status=AgentStatus.OK, confidence=0.0,
            )

        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.OK,
            confidence=best.similarity,
            findings=[
                Finding(
                    label=signals.F_SCRIPT_MATCH,
                    value=best.label,
                    confidence=best.similarity,
                    source=f"scripts:{best.backend}",
                    # The template itself, so the claim is followable: a
                    # similarity with nothing to compare against is a number
                    # the reader has to take on trust.
                    detail=f"turn {best_turn}: {best.template}",
                )
            ],
            features={signals.K_SCRIPT_SIMILARITY: best.similarity},
            provenance=[f"scripts:{best.backend}"],
        )


__all__ = ["ScriptMatchAgent"]
