"""
Entity extraction, as a graph agent (T-18, audit B-03).

**Why it exists.** An investigation is about the identifiers in the evidence —
the number to call back, the VPA to pay, the link to open. The input classifier
already *detected* that a message held a URL, a UPI ID and a phone number, and
`state.entities` still came back empty, because no agent in the graph wrote it.
The legacy `/api/analyze` path and the knowledge graph extract the same things
with `intel/entities.py`; this agent is that extractor, reached from the graph.

**What it consumes.** Every piece of text the investigation holds, each with
the id of what it came from: the inline text of each `EvidenceItem` (a pasted
message, or a bare URL / number / VPA submitted as its own item),
`extracted_text` by its `source_ref`, and a final `transcript`.

**What it outputs.** One `entity` finding per identifier — `value` is
`kind:value`, `detail` the evidence item it was found in — and a count per kind
as features. `state_update` folds the findings into `state.entities`, the
contract's flat, deduplicated `EntitySet`.

**How it connects.** EXTRACT tier, so every later tier reads `state.entities`.
It writes nothing else. The spoofing agent deliberately does *not* treat these
numbers as the caller's: a number written in a message is a call-back number,
not caller ID (`inherited/conversation.phone_numbers`).

**How it is evaluated.** `test_entity_agent.py`: a message with a link, a VPA
and a number yields all three with their source item; a bank debit SMS with a
masked account number yields no phone and no account; an extractor that raises
leaves the investigation complete and tagged; and the lifecycle API returns the
entities.

**Limitations, stated.** Regexes, conservative on purpose (a false entity is a
false graph edge — see `intel/entities.py`). No canonicalisation or cross-case
lookup (T-34). It runs in the same tier as a future OCR agent, so text an OCR
agent recovers is read only once extraction moves after it — the reason the
EXTRACT tier will need an order when that agent exists.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from schema.models import AgentResult, AgentStatus, EntitySet, Finding, InvestigationState

from ...intel.entities import extract_from_text, extract_urls
from .. import registry
from ..base import AgentContext, Stage

NAME = "entity_extractor"
F_ENTITY = "entity"

#: The `EntitySet` fields this agent fills, in the order findings are emitted.
_KINDS = (
    "phones", "upi_ids", "emails", "wallets", "bank_accounts", "domains", "urls",
    "authorities", "banks", "locations", "scam_keywords", "amounts",
)


def _sources(state: InvestigationState) -> Iterable[Tuple[str, str]]:
    """(source id, text) for every readable piece of evidence."""
    for item in state.inputs:
        if item.text and item.text.strip():
            yield item.id, item.text
    for extracted in state.extracted_text:
        if extracted.text and extracted.text.strip():
            yield extracted.source_ref, extracted.text
    if state.transcript is not None and state.transcript.final:
        yield "transcript", "\n".join(u.text for u in state.transcript.final if u.text)


@registry.register
class EntityExtractorAgent:
    """Pulls the identifiers out of the evidence and into `state.entities`."""

    name = NAME
    version = "1.0.0"
    stage = Stage.EXTRACT
    writes = ("entities",)

    def can_handle(self, state: InvestigationState) -> bool:
        return any(True for _ in _sources(state))

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        findings: List[Finding] = []
        seen: set[Tuple[str, str]] = set()
        for source, text in _sources(state):
            found = extract_from_text(text).as_dict()
            found["urls"] = extract_urls(text)
            for kind in _KINDS:
                for value in found.get(kind, []):
                    key = (kind, str(value))
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(
                        Finding(
                            label=F_ENTITY,
                            value=f"{kind}:{value}",
                            confidence=1.0,
                            source="intel.entities",
                            detail=source,
                        )
                    )

        counts: Dict[str, float] = {f"entities_{kind}": 0.0 for kind in _KINDS}
        for (kind, _value) in seen:
            counts[f"entities_{kind}"] += 1.0
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.OK,
            confidence=1.0,
            findings=findings,
            features=counts,
            provenance=["intel.entities"],
        )

    def state_update(self, state: InvestigationState, result: AgentResult) -> Dict[str, object]:
        """`state.entities`, rebuilt from this result's findings alone."""
        collected: Dict[str, list] = {kind: [] for kind in _KINDS}
        for finding in result.findings:
            if finding.label != F_ENTITY or not finding.value or ":" not in finding.value:
                continue
            kind, value = finding.value.split(":", 1)
            if kind == "amounts":
                collected[kind].append(float(value))
            elif kind in collected:
                collected[kind].append(value)
        return {"entities": EntitySet(**collected)}


__all__ = ["F_ENTITY", "EntityExtractorAgent"]
