"""
Threat fusion, as an agent — and the one place the seven signals meet.

**Why it exists.** `engine/threat.py` is where the number on the meter comes
from, and its two load-bearing properties are that every point is attributable
to a named driver and that the score ratchets. The graph could reach every
input to it and none of the fusion.

**What it consumes.** Only what the earlier tiers *published* — never their
internals. It replays the `stage` findings and the `victim_state` findings
through a fresh `ManipulationAccumulator`, and reads `coercion_index`,
`trust_pct`, `spoofing_risk` and `script_similarity` as features.

**What it outputs.** `threat_score` and the five manipulation bars as features,
the fused drivers as findings, and the band as `threat_level`. `provenance`
names which of the five signals it actually had and `confidence` is the fraction
of them it reached, so a fusion over two inputs cannot be mistaken for a fusion
over five.

**How it connects.** It is the first occupant of the JUDGE tier, which was
built empty in 1.3. Task 4.6 is what eventually fills that tier properly, and
this adapter is then either one input to the calibrated fusion or retired by it.

**How it is evaluated.** `test_inherited_agents.py` asserts the fused score,
level, drivers and manipulation map equal `engine/analyzer.analyze_text`'s on
the same input — the whole point of 1.7 expressed as an equality.

**Limitations, stated — and this is the important part of this file.**

*It does not write `state.risk_score`.* The contract's score is task 4.6's to
fill, from a calibrated model plus deterministic rules plus graph evidence.
Filling it here from a heuristic weighted sum would put an unearned number in
the field the report reads first, and CLAUDE.md is explicit that a model that
has not been evaluated does not get to advertise the capability. So the fused
score travels as a *feature*: available to 4.1's assembly, visible in the
trace, and not yet a claim.

*It does not apply the dispositive floor.* `analyze_text` escalates the score
when a check is conclusive on its own — a credential request does not become
less dispositive because the surrounding text was polite. That escalation is a
deterministic rule, and ARCHITECTURE.md §4 puts deterministic rules inside the
fusion box that 4.6 builds. Reimplementing the formula here would give the
project two copies of it, which is how the two paths start disagreeing about a
69.6. The passport and spoofing agents publish the FAILs the rule acts on; the
rule stays where the architecture put it. Concretely: on evidence with a
dispositive FAIL this agent's `threat_score` is *lower* than what
`/api/analyze/text` returns for the same text, and that difference is the floor
not yet being applied rather than a disagreement between the paths.

Why the accumulator is replayed rather than passed
--------------------------------------------------
`threat.fuse` wants a `ManipulationAccumulator`, which is charged by the
caller's stages *and* the victim's states, interleaved in call order. Two
concurrent agents produce those two halves and neither can hold the object.
Passing it is impossible — only an `AgentResult` crosses between agents — so it
is rebuilt here by calling the accumulator's own public methods over the
published findings. That keeps the charge constants in `threat.py`, where a
copy of `0.34` in this file would eventually drift from.

Replaying in publication order is faithful for a reason worth writing down:
every charge is `min(1.0, current + delta)` with non-negative deltas, so the
final value depends on the multiset of deltas and not on their order. The test
asserts the resulting map equals the interleaved one rather than relying on
that argument.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState

from ...engine.threat import ManipulationAccumulator, fuse
from .. import registry
from ..base import AgentContext, Stage
from . import signals


def _accumulator(state: InvestigationState) -> ManipulationAccumulator:
    """Rebuild the manipulation pressure from what the REASON tier published."""
    accumulator = ManipulationAccumulator()
    stage_result = signals.result_of(state, signals.STAGE_CLASSIFIER)
    for finding in signals.findings(stage_result, signals.F_STAGE):
        if finding.value:
            accumulator.observe(finding.value, finding.confidence)

    coercion_result = signals.result_of(state, signals.COERCION_TRACKER)
    for finding in signals.findings(coercion_result, signals.F_VICTIM_STATE):
        if finding.value:
            accumulator.observe_victim(finding.value)
    return accumulator


@registry.register
class ThreatFusionAgent:
    """Combines the conversational signals and the number metadata into one score."""

    name = signals.THREAT_FUSION
    version = "1.0.0"
    stage = Stage.JUDGE

    def can_handle(self, state: InvestigationState) -> bool:
        """Only once something has been classified.

        Fusing over an empty tier would produce a confident zero, which is the
        shape of a false negative. No stage, no fusion.
        """
        return signals.answered(signals.result_of(state, signals.STAGE_CLASSIFIER))

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        stage_result = signals.result_of(state, signals.STAGE_CLASSIFIER)
        coercion_result = signals.result_of(state, signals.COERCION_TRACKER)
        passport_result = signals.result_of(state, signals.TRUST_PASSPORT)
        script_result = signals.result_of(state, signals.SCRIPT_MATCH)
        spoof_result = signals.result_of(state, signals.NUMBER_SPOOFING)

        peak = signals.first_finding(stage_result, signals.F_PEAK_STAGE)
        script = signals.first_finding(script_result, signals.F_SCRIPT_MATCH)

        # `coercion_index` is 0.0 rather than None when the coercion agent
        # skipped, and that is faithful rather than sloppy: `fuse` types it as a
        # plain float because the engine has no "not measured" value for it, and
        # a conversation with no victim turn genuinely contributes nothing. The
        # two signals that *do* have an unrun value — trust and spoofing — are
        # passed as None below, which is what keeps an absent number from
        # reading as a clean one.
        coercion_index = signals.feature(coercion_result, signals.K_COERCION_INDEX) or 0.0
        trust_pct: Optional[float] = signals.feature(passport_result, signals.K_TRUST_PCT)
        spoofing_risk: Optional[float] = signals.feature(spoof_result, signals.K_SPOOFING_RISK)
        similarity = signals.feature(script_result, signals.K_SCRIPT_SIMILARITY)

        accumulator = _accumulator(state)
        result = fuse(
            stage=peak.value if peak and peak.value else "BENIGN",
            stage_confidence=peak.confidence if peak else 0.0,
            manipulation=accumulator,
            coercion_index=coercion_index,
            trust_pct=trust_pct,
            spoofing_risk=spoofing_risk,
            script_similarity=similarity,
            script_label=script.value if script else None,
            # A batch investigation has no previous frame and no elapsed time,
            # so the ratchet has nothing to hold up. The live path is where
            # those arguments earn their keep.
            previous_score=0.0,
            dt_s=0.0,
        )

        findings: List[Finding] = [
            Finding(
                label=signals.F_THREAT_DRIVER,
                value=driver.label,
                confidence=round(driver.contribution, 3),
                source="threat_fusion",
                detail=driver.detail,
            )
            for driver in result.drivers
        ]
        findings.append(
            Finding(
                label=signals.F_THREAT_LEVEL,
                value=result.level,
                confidence=1.0,
                source="threat_fusion",
                detail=f"{result.score:.1f}/100 from {len(result.drivers)} driver(s)",
            )
        )

        features: Dict[str, float] = {
            signals.K_THREAT_SCORE: result.score,
            signals.K_TACTIC_PRESSURE: round(accumulator.pressure, 3),
        }
        for tactic, value in accumulator.as_dict().items():
            features[f"{signals.MANIPULATION_PREFIX}{tactic}"] = value

        provenance = [
            name
            for name, present in (
                (signals.STAGE_CLASSIFIER, signals.answered(stage_result)),
                (signals.COERCION_TRACKER, signals.answered(coercion_result)),
                (signals.TRUST_PASSPORT, signals.answered(passport_result)),
                (signals.SCRIPT_MATCH, signals.answered(script_result)),
                (signals.NUMBER_SPOOFING, signals.answered(spoof_result)),
            )
            if present
        ]

        # DEGRADED only when a contributing agent *ran and failed*. A signal
        # that is simply absent is not a degradation: a forwarded SMS has no
        # victim side, so the coercion tracker correctly does not apply, and
        # marking every SMS investigation degraded for it would be exactly the
        # `degraded` field people learn to ignore. How much this fusion had is
        # already said precisely, twice — `provenance` names the signals it used
        # and `confidence` is the fraction of five it reached.
        failed = [
            result.agent
            for result in state.agent_results
            if result.status is AgentStatus.ERROR
            and result.agent in {
                signals.STAGE_CLASSIFIER,
                signals.COERCION_TRACKER,
                signals.TRUST_PASSPORT,
                signals.SCRIPT_MATCH,
                signals.NUMBER_SPOOFING,
            }
        ]
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.DEGRADED if failed else AgentStatus.OK,
            confidence=round(len(provenance) / 5.0, 3),
            findings=findings,
            features=features,
            provenance=provenance,
            error=("fused without " + ", ".join(sorted(failed))) if failed else None,
        )


__all__ = ["ThreatFusionAgent", "_accumulator"]
