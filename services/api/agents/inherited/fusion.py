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

*It writes `state.risk_score`, provisionally.* Until 2026-10-22 it did not:
the contract's score was to come from a calibrated model, and a heuristic sum
in that field would have been an unearned number. The cost was audit item
B-02 — the same digital-arrest message read 93 CRITICAL on `/api/analyze/text`
and *unscored* in an investigation, with this agent reporting a third answer
(ELEVATED, its pre-floor band). The owner decided (Q4, 2026-10-09) to show the
score tagged uncalibrated. So this agent now writes `risk_score` and
`risk_level`, and declares `score:uncalibrated` as a tag that travels with
every score it writes; the report says it in words. It is replaced, not
extended, by the calibrated judge (T-41, T-42).

*It applies the dispositive floor by calling the analyzer's own functions.*
`analyze_text` escalates the score when a check is conclusive on its own — a
credential request does not become less dispositive because the surrounding
text was polite. Rather than a second copy of that rule, this agent calls
`analyzer.dispositive_floor` with the weights in `analyzer.DISPOSITIVE_CHECKS`
and `DISPOSITIVE_SPOOF_CHECKS` for the FAILs the passport and spoofing agents
published, plus `analyzer.text_findings` over the same text. One rule, reached
two ways — which is what the parity test asserts.

*It does not classify.* `classification` stays None: no rule maps the scam arc
onto the twelve fraud categories, and inventing one here would be a new rule
outside this task (T-20) — it is the calibrated judge's.

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

from schema.models import AgentResult, AgentStatus, Finding, InvestigationState, ThreatLevel

from ...engine.analyzer import (
    DISPOSITIVE_CHECKS,
    DISPOSITIVE_SPOOF_CHECKS,
    dispositive_floor,
    text_findings,
)
from ...engine.threat import ManipulationAccumulator, fuse, level_of
from .. import registry
from ..base import AgentContext, Stage
from . import conversation, signals


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
    version = "2.0.0"
    stage = Stage.JUDGE
    #: The provisional judge (T-20). Every score it writes carries the tag.
    writes = ("risk_score", "risk_level")
    write_tags = ("score:uncalibrated",)

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

        conclusive = _dispositive(state, passport_result, spoof_result)
        risk = dispositive_floor(result.score, [f.confidence for f in conclusive])
        level = level_of(risk)

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
        findings.extend(conclusive)
        findings.append(
            Finding(
                label=signals.F_THREAT_LEVEL,
                value=level,
                confidence=1.0,
                source="threat_fusion",
                detail=(
                    f"{risk:.1f}/100 from {len(result.drivers)} driver(s)"
                    + (f" and {len(conclusive)} conclusive check(s)" if conclusive else "")
                    + " — uncalibrated"
                ),
            )
        )

        features: Dict[str, float] = {
            signals.K_THREAT_SCORE: result.score,
            signals.K_RISK_SCORE: risk,
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


    def state_update(self, state: InvestigationState, result: AgentResult) -> Dict[str, object]:
        risk = result.features.get(signals.K_RISK_SCORE)
        if risk is None:
            return {}
        return {"risk_score": risk, "risk_level": ThreatLevel(level_of(risk))}


def _dispositive(
    state: InvestigationState,
    passport_result: Optional[AgentResult],
    spoof_result: Optional[AgentResult],
) -> List[Finding]:
    """The conclusive checks behind the floor, as findings the report can cite.

    The same three sources `analyze_text` floors on: the passport's dispositive
    FAILs, the payment framing and VPA findings over the evidence text, and the
    number checks that settle a verdict alone. Weights come from the analyzer's
    own tables, so the two paths cannot weigh one check differently.
    """
    out: List[Finding] = []
    for f in signals.findings(passport_result, signals.F_PASSPORT_FAIL):
        if f.value in DISPOSITIVE_CHECKS:
            out.append(_conclusive(f.value, DISPOSITIVE_CHECKS[f.value], f.detail, f.source))

    claimed = signals.first_finding(passport_result, "claimed_identity")
    framed, _ = text_findings(
        conversation.source_text(state), claimed.value if claimed else None
    )
    for item in framed:
        if item.verdict == "FAIL":
            out.append(_conclusive(item.label, item.weight, item.detail, item.source))

    for f in signals.findings(spoof_result, signals.F_NUMBER_FAIL):
        if f.value in DISPOSITIVE_SPOOF_CHECKS:
            out.append(
                _conclusive(f"Number: {f.value}", DISPOSITIVE_SPOOF_CHECKS[f.value], f.detail, f.source)
            )
    return out


def _conclusive(name: str, weight: float, detail: Optional[str], source: Optional[str]) -> Finding:
    return Finding(
        label=signals.F_DISPOSITIVE,
        value=name,
        confidence=weight,
        source=source or "threat_fusion",
        detail=detail,
    )


__all__ = ["ThreatFusionAgent", "_accumulator"]
