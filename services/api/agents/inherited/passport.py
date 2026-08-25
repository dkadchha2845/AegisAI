"""
The Trust Passport, as an agent.

**Why it exists.** It is the mechanical half of the verdict: not "does this
caller sound suspicious", which is not checkable, but "did this caller ask for
an OTP", which is. Six checks, each PASS / FAIL / UNKNOWN, each non-UNKNOWN
verdict carrying the knowledge-base document that backed it — which is what
lets a report cite a source for every claim rather than asserting one.

**What it consumes.** The caller's turns, from `conversation.py`.

**What it outputs.** One finding per check, labelled by verdict so
`EvidenceStore.findings(label="passport_fail")` answers "which of this
organisation's cases involved a credential request" without loading a case;
plus `trust_pct`, computed over *resolved* checks only.

**How it connects.** `threat_fusion` reads `trust_pct` and passes it to
`threat.fuse`, which gives failed identity checks 15% of the four-signal sum.
The dispositive escalation `analyze_text` applies on top of that — a credential
request flooring the score regardless of how polite the rest was — is
deliberately *not* applied here; it is a deterministic rule, and
ARCHITECTURE.md §4 puts those inside the fusion box that task 4.6 builds. The
findings this agent publishes are the material that rule acts on.

**How it is evaluated.** `test_inherited_agents.py` asserts the checks and the
trust percentage equal `analyze_text`'s on the same input, and that the benign
bank reminder — "we will never ask for your OTP" — resolves nothing as a FAIL.
That case is not decoration: matching the bare word `OTP` once flagged a real
reminder call as CRITICAL, which is the exact false positive that teaches people
to ignore the system.

**Limitations, stated.** Every check is a regex over Hinglish and English, so a
scam conducted in a language the patterns do not cover resolves nothing and the
passport honestly reads 50% — unevaluated, neither trusted nor fraudulent.
Checks latch: a caller who asked for an OTP at 0:40 does not become trustworthy
by not asking again at 1:20, which is correct for a call and means this agent's
result is order-dependent within one investigation, though not across two.
"""

from __future__ import annotations

from typing import Dict, List

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState

from ...engine.passport import TrustPassport
from ...rag.store import get_kb
from .. import registry
from ..base import AgentContext, Stage
from . import conversation, signals

#: Verdict -> the label its finding is published under. Split so a verdict is a
#: label query rather than a scan through every finding's value.
_LABEL_BY_VERDICT = {
    "FAIL": signals.F_PASSPORT_FAIL,
    "PASS": signals.F_PASSPORT_PASS,
    "UNKNOWN": signals.F_PASSPORT_UNKNOWN,
}


@registry.register
class TrustPassportAgent:
    """Checks a caller's claimed identity against what institutions actually do."""

    name = signals.TRUST_PASSPORT
    version = "1.0.0"
    stage = Stage.REASON

    def can_handle(self, state: InvestigationState) -> bool:
        return conversation.has_caller_speech(state)

    async def warmup(self) -> None:
        """Build the knowledge base before an investigation waits on it.

        Measured, not assumed: the first run of this agent in a cold process
        took **7 224 ms**, against a default node budget of 8 000. Every FAIL
        this agent publishes carries a citation, and fetching one is
        `get_kb().search(...)`, which builds the retrieval index on first use.
        The API already warms the same singleton at startup, so this is the
        graph-side half of a discipline the service already had — and it is what
        makes the agent 7 ms instead of 7 seconds on a worker or in the CLI.
        """
        get_kb()

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        passport = TrustPassport()
        for turn in conversation.caller_turns(state):
            passport.observe(turn.text, conversation.CALLER)
        snapshot = passport.snapshot()

        findings: List[Finding] = [
            Finding(
                label=_LABEL_BY_VERDICT[check.verdict],
                value=check.name,
                # An unresolved check carries no confidence, because it carries
                # no evidence — that is what UNKNOWN means here.
                confidence=1.0 if check.verdict != "UNKNOWN" else 0.0,
                source=check.source or "trust_passport",
                detail=check.detail,
            )
            for check in snapshot.checks
        ]
        if snapshot.claimed_identity:
            findings.append(
                Finding(
                    label="claimed_identity",
                    value=snapshot.claimed_identity,
                    confidence=1.0,
                    source="trust_passport",
                    detail="claimed on the call; unverifiable from the call itself",
                )
            )

        fails = sum(1 for c in snapshot.checks if c.verdict == "FAIL")
        features: Dict[str, float] = {
            signals.K_TRUST_PCT: snapshot.final_trust_pct,
            signals.K_PASSPORT_FAILS: float(fails),
        }

        # Confidence is how much of the passport actually resolved, not how bad
        # the news is. A passport with one FAIL out of one resolved check is a
        # confident 0% trust; one with six UNKNOWNs is not confident at all.
        resolved = sum(1 for c in snapshot.checks if c.verdict != "UNKNOWN")
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.OK,
            confidence=round(resolved / len(snapshot.checks), 3) if snapshot.checks else 0.0,
            findings=findings,
            features=features,
            provenance=["trust_passport", "knowledge_base"],
        )


__all__ = ["TrustPassportAgent"]
